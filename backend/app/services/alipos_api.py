import asyncio
import datetime
import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level token cache
_token: str | None = None
_token_expires_at: float = 0

# Menu cache (5 minute TTL)
_menu_cache: dict | None = None
_menu_cache_expires_at: float = 0
_MENU_TTL = 300

# Availability changes more frequently than menu composition.
_availability_cache: dict | None = None
_availability_cache_expires_at: float = 0
_AVAILABILITY_TTL = 30

# Halls/tables cache (5 minute TTL)
_tables_cache: dict | None = None
_tables_cache_expires_at: float = 0
_tables_cache_last_success_at: datetime.datetime | None = None


@dataclass(frozen=True)
class HallsTablesSnapshot:
    payload: dict
    stale: bool
    last_success_at: datetime.datetime


class HallsTablesUnavailable(RuntimeError):
    pass


class AliPOSRejected(RuntimeError):
    """AliPOS returned a definite HTTP error before accepting the order."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"AliPOS rejected the order (HTTP {status_code})")


class AliPOSPreSubmitError(RuntimeError):
    """A prerequisite failed before the order POST could be attempted."""

    def __init__(self, status_code: int | None = None) -> None:
        self.status_code = status_code
        detail = "AliPOS order submission prerequisite failed"
        if status_code is not None:
            detail = f"{detail} (HTTP {status_code})"
        super().__init__(detail)


class AliPOSUnknownOutcome(RuntimeError):
    """The create request may have reached AliPOS, so it must not be retried."""


def _format_alipos_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text.strip()

    if isinstance(payload, dict):
        for key in ("message", "detail", "title", "error"):
            value = payload.get(key)
            if value:
                return str(value)
        return str(payload)

    if isinstance(payload, list):
        return str(payload)

    return payload or response.reason_phrase


async def _get_token() -> str:
    """Get a valid AliPOS access token, refreshing if expired."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.alipos_api_base_url}/security/oauth/token",
            data={
                "client_id": settings.alipos_api_client_id,
                "client_secret": settings.alipos_api_client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    _token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 86400)
    return _token


async def _api_request(
    method: str,
    path: str,
    *,
    pre_submit: bool = False,
    **kwargs,
) -> httpx.Response:
    """Make an authenticated request to the AliPOS API with retry."""
    try:
        token = await _get_token()
    except Exception as exc:
        if not pre_submit:
            raise
        status_code = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        )
        raise AliPOSPreSubmitError(status_code) from exc
    max_retries = 3
    last_exc: BaseException | None = None

    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.request(
                    method,
                    f"{settings.alipos_api_base_url}{path}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                    timeout=30,
                    follow_redirects=True,
                    **kwargs,
                )
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                if pre_submit:
                    logger.warning(
                        "AliPOS prerequisite request rejected: %s %s -> %s",
                        method,
                        path,
                        exc.response.status_code,
                    )
                    raise AliPOSPreSubmitError(exc.response.status_code) from exc
                detail = _format_alipos_error(exc.response)
                logger.warning(
                    "AliPOS API returned HTTP error: %s %s -> %s (%s)",
                    method,
                    path,
                    exc.response.status_code,
                    detail,
                )
                raise RuntimeError(
                    f"AliPOS returned {exc.response.status_code}: {detail}"
                ) from exc
            except httpx.RequestError as exc:
                last_exc = exc
                if pre_submit:
                    logger.warning(
                        "AliPOS prerequisite request transport failure: "
                        "%s %s (attempt %d/%d)",
                        method,
                        path,
                        attempt + 1,
                        max_retries,
                    )
                else:
                    logger.warning(
                        "AliPOS request failed (attempt %d/%d): %s %s -> %s",
                        attempt + 1,
                        max_retries,
                        method,
                        path,
                        exc,
                    )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

    if pre_submit:
        raise AliPOSPreSubmitError() from last_exc
    raise RuntimeError(
        f"AliPOS request failed after {max_retries} attempts: {last_exc}"
    ) from last_exc


async def get_menu() -> dict:
    """Fetch the full menu for the configured restaurant, cached for 5 minutes."""
    global _menu_cache, _menu_cache_expires_at
    if _menu_cache is not None and time.monotonic() < _menu_cache_expires_at:
        return _menu_cache
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/menu/{settings.alipos_restaurant_id}/composition",
    )
    _menu_cache = resp.json()
    _menu_cache_expires_at = time.monotonic() + _MENU_TTL
    return _menu_cache


async def get_menu_availability() -> dict:
    """Fetch live item/modifier availability, cached briefly."""
    global _availability_cache, _availability_cache_expires_at
    if (
        _availability_cache is not None
        and time.monotonic() < _availability_cache_expires_at
    ):
        return _availability_cache
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/menu/{settings.alipos_restaurant_id}/availability",
    )
    _availability_cache = resp.json()
    _availability_cache_expires_at = time.monotonic() + _AVAILABILITY_TTL
    return _availability_cache


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _decode_halls_tables(response) -> dict:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("AliPOS table directory must be an object")
    if not isinstance(payload.get("halls"), list):
        raise ValueError("AliPOS table directory halls must be a list")
    if not isinstance(payload.get("tables"), list):
        raise ValueError("AliPOS table directory tables must be a list")
    hall_ids: set[uuid.UUID] = set()
    for index, hall in enumerate(payload["halls"]):
        if not isinstance(hall, dict):
            raise ValueError(f"AliPOS hall {index} must be an object")
        if not isinstance(hall.get("title"), str):
            raise ValueError(f"AliPOS hall {index} is malformed")
        try:
            hall_id = uuid.UUID(str(hall["id"]))
            service_percent = Decimal(str(hall.get("servicePercent") or 0))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"AliPOS hall {index} is malformed") from exc
        if not service_percent.is_finite() or hall_id in hall_ids:
            raise ValueError(f"AliPOS hall {index} is malformed")
        hall_ids.add(hall_id)
    table_ids: set[uuid.UUID] = set()
    for index, table in enumerate(payload["tables"]):
        if not isinstance(table, dict):
            raise ValueError(f"AliPOS table {index} must be an object")
        if not isinstance(table.get("title"), str):
            raise ValueError(f"AliPOS table {index} is malformed")
        try:
            table_id = uuid.UUID(str(table["id"]))
            hall_id = uuid.UUID(str(table["hallId"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"AliPOS table {index} is malformed") from exc
        if table_id in table_ids or hall_id not in hall_ids:
            raise ValueError(f"AliPOS table {index} is malformed")
        table_ids.add(table_id)
    return payload


async def get_halls_and_tables_snapshot() -> HallsTablesSnapshot:
    global _tables_cache, _tables_cache_expires_at, _tables_cache_last_success_at

    if _tables_cache is not None and time.monotonic() < _tables_cache_expires_at:
        if _tables_cache_last_success_at is None:
            raise HallsTablesUnavailable("Table cache is missing freshness metadata")
        return HallsTablesSnapshot(
            _tables_cache,
            False,
            _tables_cache_last_success_at,
        )

    try:
        response = await _api_request(
            "GET",
            f"/api/Integration/v1/restaurant/{settings.alipos_restaurant_id}/halls-and-tables",
        )
        payload = _decode_halls_tables(response)
    except Exception as exc:
        if _tables_cache is None or _tables_cache_last_success_at is None:
            raise HallsTablesUnavailable("Table directory is unavailable") from exc
        return HallsTablesSnapshot(
            _tables_cache,
            True,
            _tables_cache_last_success_at,
        )

    _tables_cache = payload
    _tables_cache_expires_at = time.monotonic() + _MENU_TTL
    _tables_cache_last_success_at = _utcnow()
    return HallsTablesSnapshot(
        _tables_cache,
        False,
        _tables_cache_last_success_at,
    )


async def get_halls_and_tables() -> dict:
    snapshot = await get_halls_and_tables_snapshot()
    if snapshot.stale:
        # Stale fallback is inspection-only. Customer resolution and token
        # restoration must never accept a table removed from the live directory.
        raise HallsTablesUnavailable("A fresh table directory is required")
    return snapshot.payload


async def create_order(order_payload: dict) -> dict:
    """Send one order create attempt; an unknown outcome is never retried."""
    try:
        token = await _get_token()
    except AliPOSPreSubmitError:
        raise
    except Exception as exc:
        status_code = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        )
        raise AliPOSPreSubmitError(status_code) from exc
    path = "/api/Integration/v1/order"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                "POST",
                f"{settings.alipos_api_base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                json=order_payload,
                timeout=30,
                follow_redirects=True,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AliPOSRejected(exc.response.status_code) from exc
    except httpx.RequestError as exc:
        raise AliPOSUnknownOutcome("AliPOS order create outcome is unknown") from exc
    return resp.json()


async def get_order_status(alipos_order_id: str) -> dict:
    """Fetch order details from AliPOS."""
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/order/{alipos_order_id}",
    )
    return resp.json()


async def cancel_order(alipos_order_id: str, comment: str) -> None:
    """Cancel an order once with AliPOS's required comment body."""
    token = await _get_token()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                f"{settings.alipos_api_base_url}/api/Integration/v1/order/{alipos_order_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                json={"comment": comment},
                timeout=30,
                follow_redirects=True,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _format_alipos_error(exc.response)
        raise RuntimeError(
            f"AliPOS returned {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError("AliPOS cancellation outcome is unknown") from exc


async def get_payment_methods() -> list[dict]:
    """Fetch available payment methods."""
    resp = await _api_request(
        "GET",
        "/api/Integration/v1/paymentMethod/all",
        pre_submit=True,
    )
    return resp.json()
