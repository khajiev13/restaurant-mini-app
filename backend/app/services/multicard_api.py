import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level token cache
_mc_token: str | None = None
_mc_token_expires_at: float = 0


class RefundRejected(RuntimeError):
    """Multicard definitely rejected a refund request."""

    def __init__(self, status_code: int | None = None):
        message = "Multicard refund was rejected"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        super().__init__(message)
        self.status_code = status_code


class RefundOutcomeUnknown(RuntimeError):
    """A refund may have completed, so the payment must be reconciled."""


_AMBIGUOUS_REFUND_ERROR_CODES = frozenset(
    {
        "ERROR_UNKNOWN",
        "ERROR_CALLBACK_TIMEOUT",
        "ERROR_DEBIT_UNKNOWN",
        "ERROR_TRANS_NOT_READY",
    }
)


def _refund_error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if not isinstance(code, str) or not code.strip():
        return None
    return code.strip().upper()


async def _get_token() -> str:
    """Get a valid Multicard access token, refreshing if near-expired."""
    global _mc_token, _mc_token_expires_at

    if _mc_token and time.time() < _mc_token_expires_at - 300:
        return _mc_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.multicard_api_base_url}/auth",
            json={
                "application_id": settings.multicard_application_id,
                "secret": settings.multicard_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    # Token is in data.token or data.data.token depending on API version
    token_data = data.get("data") or data
    _mc_token = token_data["token"]
    # Multicard tokens are valid 24 hours (GMT+5). Expire after 23h to be safe.
    _mc_token_expires_at = time.time() + 23 * 3600
    return _mc_token


def verify_callback_signature(
    store_id: int,
    invoice_id: str,
    amount: int,
    received_sign: str,
) -> bool:
    """Verify Multicard success callback: MD5("{store_id}{invoice_id}{amount}{secret}")"""
    raw = f"{store_id}{invoice_id}{amount}{settings.multicard_secret}"
    expected = hashlib.md5(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, received_sign)


async def create_invoice(
    amount_tiyin: int,
    invoice_id: str,
    return_url: str,
    ttl: int = 600,
) -> dict[str, Any]:
    """Create a Multicard hosted-checkout invoice.

    Args:
        amount_tiyin: Amount in tiyin (1 UZS = 100 tiyin).
        invoice_id: Our identifier for this invoice (use order UUID string).
        return_url: Where to redirect after payment (Telegram deep link).
        ttl: Invoice validity in seconds (default 600 = 10 minutes).

    Returns:
        The invoice data dict from Multicard (includes uuid, checkout_url, short_link).

    Raises:
        RuntimeError: On API error or non-success response.
    """
    token = await _get_token()

    payload: dict[str, Any] = {
        "store_id": settings.multicard_store_id,
        "amount": amount_tiyin,
        "invoice_id": invoice_id,
        "callback_url": settings.multicard_callback_url,
        "return_url": return_url,
        "return_error_url": return_url,
        "ttl": ttl,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.multicard_api_base_url}/payment/invoice",
            json=payload,
            # Use both headers: sandbox `dev` role requires Bearer; production uses X-Access-Token.
            headers={
                "Authorization": f"Bearer {token}",
                "X-Access-Token": token,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("success"):
        err = data.get("error", {})
        raise RuntimeError(
            f"Multicard create_invoice failed: {err.get('code')} — {err.get('details')}"
        )

    invoice = data["data"]

    # Resolve the best usable checkout URL.
    # Production: checkout_url = "https://checkout.multicard.uz/invoice/{uuid}" (complete, card-first)
    # Sandbox:    uuid is null; store has old_checkout=true & disable_deeplink=true.
    #             Correct URL: "https://checkout.multicard.uz/?store_id={id}&invoice_id={invoice_id}"
    inv_uuid = invoice.get("uuid")
    checkout_url = invoice.get("checkout_url", "")

    if inv_uuid:
        if checkout_url and str(inv_uuid) not in checkout_url:
            # Safety net: UUID present but missing from URL — append it
            invoice["checkout_url"] = checkout_url.rstrip("/") + "/" + inv_uuid
        # else: checkout_url already contains the uuid (production normal case)
    else:
        # No UUID assigned (sandbox regression / old_checkout store).
        # Construct the old-style checkout URL directly — this is what the deeplink
        # redirects to anyway but avoids an extra hop and works with disable_deeplink stores.
        old_checkout_url = (
            f"https://checkout.multicard.uz/"
            f"?store_id={settings.multicard_store_id}&invoice_id={invoice_id}"
        )
        invoice["checkout_url"] = old_checkout_url
        logger.debug("No invoice UUID: using old checkout URL: %s", old_checkout_url)

    return invoice


async def cancel_invoice(invoice_uuid: str) -> None:
    """Cancel an unpaid Multicard invoice. Best-effort — logs and suppresses errors."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{settings.multicard_api_base_url}/payment/invoice/{invoice_uuid}",
                headers={"X-Access-Token": token},
                timeout=30,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # HTTP 400 = already paid or expired — not a real error for our purposes
        logger.warning(
            "Multicard cancel invoice %s: HTTP %s — %s",
            invoice_uuid,
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.warning("Multicard cancel invoice %s failed: %s", invoice_uuid, exc)


async def cancel_invoice_strict(invoice_uuid: str) -> None:
    """Cancel an unpaid invoice and fail unless Multicard confirms cancellation."""
    token = await _get_token()
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{settings.multicard_api_base_url}/payment/invoice/{invoice_uuid}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Access-Token": token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("success"):
        error = payload.get("error") or {}
        raise RuntimeError(
            "Multicard invoice cancellation failed: "
            f"{error.get('code')} — {error.get('details')}"
        )


async def refund_payment(payment_uuid: str) -> dict[str, Any]:
    """Request one full refund for a completed Multicard payment."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{settings.multicard_api_base_url}/payment/{payment_uuid}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Access-Token": token,
                },
                timeout=30,
            )
    except Exception:
        raise RefundOutcomeUnknown("Multicard refund outcome is unknown") from None

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        try:
            error_code = _refund_error_code(response.json())
        except (TypeError, ValueError):
            error_code = None
        if (
            400 <= response.status_code < 500
            and error_code is not None
            and error_code not in _AMBIGUOUS_REFUND_ERROR_CODES
        ):
            raise RefundRejected(response.status_code) from None
        raise RefundOutcomeUnknown("Multicard refund outcome is unknown") from None

    try:
        payload = response.json()
    except (TypeError, ValueError):
        raise RefundOutcomeUnknown("Multicard refund outcome is unknown") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        error_code = _refund_error_code(payload)
        if (
            isinstance(payload, dict)
            and payload.get("success") is False
            and error_code is not None
            and error_code not in _AMBIGUOUS_REFUND_ERROR_CODES
        ):
            raise RefundRejected(response.status_code)
        raise RefundOutcomeUnknown("Multicard refund outcome is unknown")
    refund = payload.get("data")
    if not isinstance(refund, dict) or str(refund.get("status") or "").casefold() != "revert":
        raise RefundOutcomeUnknown("Multicard refund outcome is unknown")
    return refund


async def get_payment(payment_uuid: str) -> dict[str, Any]:
    """Read the provider state of a payment for refund reconciliation."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.multicard_api_base_url}/payment/{payment_uuid}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Access-Token": token,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        raise RuntimeError("Multicard payment lookup failed") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Multicard payment lookup failed") from None
    payment = payload.get("data")
    if not isinstance(payment, dict):
        raise RuntimeError("Multicard payment lookup failed") from None
    return payment
