import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level token cache
_token: str | None = None
_token_expires_at: float = 0


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


async def _api_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an authenticated request to the AliPOS API with retry."""
    token = await _get_token()
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
                logger.warning(
                    "AliPOS request failed (attempt %d/%d): %s %s -> %s",
                    attempt + 1,
                    max_retries,
                    method,
                    path,
                    exc,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue

    raise RuntimeError(f"AliPOS request failed after {max_retries} attempts: {last_exc}") from last_exc


async def get_menu() -> dict:
    """Fetch the full menu for the configured restaurant."""
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/menu/{settings.alipos_restaurant_id}/composition",
    )
    return resp.json()


async def create_order(order_payload: dict) -> dict:
    """Send an order to AliPOS and return the response."""
    resp = await _api_request(
        "POST",
        "/api/Integration/v1/order",
        json=order_payload,
    )
    return resp.json()


async def get_order_status(alipos_order_id: str) -> dict:
    """Fetch order details from AliPOS."""
    resp = await _api_request(
        "GET",
        f"/api/Integration/v1/order/{alipos_order_id}",
    )
    return resp.json()


async def cancel_order(alipos_order_id: str) -> None:
    """Cancel an order in AliPOS."""
    await _api_request(
        "DELETE",
        f"/api/Integration/v1/order/{alipos_order_id}",
    )


async def get_payment_methods() -> list[dict]:
    """Fetch available payment methods."""
    resp = await _api_request(
        "GET",
        "/api/Integration/v1/paymentMethod/all",
    )
    return resp.json()
