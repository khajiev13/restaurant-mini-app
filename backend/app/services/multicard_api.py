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


class InvoicePreSubmitError(RuntimeError):
    """Invoice creation definitely did not reach the provider POST."""


class InvoiceRejected(RuntimeError):
    """Multicard definitely rejected an invoice request."""

    def __init__(self, status_code: int):
        super().__init__(f"Multicard invoice was rejected (HTTP {status_code})")
        self.status_code = status_code


class InvoiceOutcomeUnknown(RuntimeError):
    """An invoice may exist, so another POST would be unsafe."""

    def __init__(self, invoice_uuid: str | None = None):
        super().__init__("Multicard invoice outcome is unknown")
        self.invoice_uuid = invoice_uuid


class RefundRejected(RuntimeError):
    """Multicard definitely rejected a refund request."""

    def __init__(self, status_code: int | None = None):
        message = "Multicard refund was rejected"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        super().__init__(message)
        self.status_code = status_code


class RefundNotAttempted(RuntimeError):
    """A refund request definitely did not reach the provider DELETE."""


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


def _invoice_uuid(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    invoice = payload.get("data")
    if not isinstance(invoice, dict):
        return None
    value = invoice.get("uuid")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _validated_invoice(
    payload: Any,
    *,
    invoice_id: str,
    allow_uuidless: bool,
) -> dict[str, Any]:
    invoice_uuid = _invoice_uuid(payload)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise InvoiceOutcomeUnknown(invoice_uuid)
    raw_invoice = payload.get("data")
    if not isinstance(raw_invoice, dict):
        raise InvoiceOutcomeUnknown(invoice_uuid)

    invoice = dict(raw_invoice)
    if invoice_uuid is None:
        if raw_invoice.get("uuid") is not None:
            raise InvoiceOutcomeUnknown()
        if not allow_uuidless:
            raise InvoiceOutcomeUnknown()
        invoice["uuid"] = None
        invoice["checkout_url"] = (
            "https://checkout.multicard.uz/"
            f"?store_id={settings.multicard_store_id}&invoice_id={invoice_id}"
        )
        return invoice

    checkout_url = invoice.get("checkout_url")
    if not isinstance(checkout_url, str) or not checkout_url.strip():
        raise InvoiceOutcomeUnknown(invoice_uuid)
    invoice["uuid"] = invoice_uuid
    invoice["checkout_url"] = checkout_url.strip()
    return invoice


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
        InvoicePreSubmitError: Provider POST definitely did not start.
        InvoiceRejected: Provider returned one documented deterministic rejection.
        InvoiceOutcomeUnknown: An invoice may exist and must not be posted again.
    """
    post_started = False
    response: httpx.Response | None = None
    try:
        payload: dict[str, Any] = {
            "store_id": settings.multicard_store_id,
            "amount": amount_tiyin,
            "invoice_id": invoice_id,
            "callback_url": settings.multicard_callback_url,
            "return_url": return_url,
            "return_error_url": return_url,
            "ttl": ttl,
        }
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            post_started = True
            response = await client.post(
                f"{settings.multicard_api_base_url}/payment/invoice",
                json=payload,
                # Sandbox `dev` uses Bearer; production accepts X-Access-Token.
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Access-Token": token,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
    except Exception:
        if not post_started:
            raise InvoicePreSubmitError(
                "Multicard invoice request was not attempted"
            ) from None
        response_payload = None
        if response is not None:
            try:
                response_payload = response.json()
            except (TypeError, ValueError):
                pass
        raise InvoiceOutcomeUnknown(_invoice_uuid(response_payload)) from None

    try:
        response_payload = response.json()
    except (TypeError, ValueError):
        raise InvoiceOutcomeUnknown() from None

    error_code = _refund_error_code(response_payload)
    definite_rejection = (
        isinstance(response_payload, dict)
        and response_payload.get("success") is False
        and (
            (response.status_code == 400 and error_code == "ERROR_FIELDS")
            or (response.status_code == 404 and error_code == "ERROR_NOT_FOUND")
        )
    )
    if definite_rejection:
        raise InvoiceRejected(response.status_code)
    if not 200 <= response.status_code < 300:
        raise InvoiceOutcomeUnknown(_invoice_uuid(response_payload))
    return _validated_invoice(
        response_payload,
        invoice_id=invoice_id,
        allow_uuidless=settings.multicard_allow_uuidless_sandbox_checkout,
    )


async def get_invoice(invoice_uuid: str) -> dict[str, Any]:
    """Read one known invoice without creating a replacement."""
    try:
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.multicard_api_base_url}/payment/invoice/{invoice_uuid}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Access-Token": token,
                },
                timeout=30,
            )
        if not 200 <= response.status_code < 300:
            raise RuntimeError
        payload = response.json()
        invoice = _validated_invoice(
            payload,
            invoice_id="",
            allow_uuidless=False,
        )
        if invoice["uuid"] != invoice_uuid:
            raise RuntimeError
        return invoice
    except Exception:
        raise RuntimeError("Multicard invoice lookup failed") from None


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
    delete_invocation_started = False
    try:
        token = await _get_token()
        async with httpx.AsyncClient() as client:
            delete_invocation_started = True
            response = await client.delete(
                f"{settings.multicard_api_base_url}/payment/{payment_uuid}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Access-Token": token,
                },
                timeout=30,
            )
    except Exception:
        if not delete_invocation_started:
            raise RefundNotAttempted("Multicard refund was not attempted") from None
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
