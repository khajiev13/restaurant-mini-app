import datetime
import hmac
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.models import Order, Stoplist, User
from app.services import multicard_api
from app.services.order_service import dispatch_queued_alipos_order
from app.services.order_status_service import (
    apply_alipos_status_update_for_order,
    parse_alipos_updated_at,
)
from app.services.phone_verification_service import (
    InvalidPhoneNumber,
    is_newer_contact_update,
    normalize_phone_number,
    phone_verification_fingerprint,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _mask_telegram_id(telegram_id: Any) -> str:
    value = str(telegram_id)
    if len(value) <= 4:
        return value
    return f"***{value[-4:]}"


def _log_telegram_webhook_outcome(
    outcome: str,
    update_id: object,
    started_at: float,
    telegram_id: int | None = None,
) -> None:
    logger.info(
        "Telegram bot webhook outcome=%s update_id=%s telegram_user_id=%s duration_ms=%s",
        outcome,
        update_id if type(update_id) is int else "unknown",
        _mask_telegram_id(telegram_id) if telegram_id is not None else "unknown",
        round((time.perf_counter() - started_at) * 1000),
    )


def _verify_webhook_credentials(
    client_id: str | None, client_secret: str | None
) -> None:
    """Verify that AliPOS webhook headers match our credentials."""
    import hmac as _hmac

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials"
        )

    id_ok = _hmac.compare_digest(client_id, settings.alipos_api_client_id)
    secret_ok = _hmac.compare_digest(client_secret, settings.alipos_api_client_secret)
    if not id_ok or not secret_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )


@router.post("/bot")
async def telegram_bot_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict:
    """Receive Telegram bot updates (contact messages)."""
    started_at = time.perf_counter()
    webhook_secret = settings.telegram_webhook_secret
    if not webhook_secret:
        _log_telegram_webhook_outcome("secret_not_configured", None, started_at)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook secret is not configured",
        )
    try:
        secret_is_valid = bool(x_telegram_bot_api_secret_token) and hmac.compare_digest(
            x_telegram_bot_api_secret_token, webhook_secret
        )
    except TypeError:
        secret_is_valid = False
    if not secret_is_valid:
        _log_telegram_webhook_outcome("invalid_secret", None, started_at)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret"
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        _log_telegram_webhook_outcome("invalid_json", None, started_at)
        return {"result": "OK"}
    if not isinstance(body, dict):
        _log_telegram_webhook_outcome("invalid_structure", None, started_at)
        return {"result": "OK"}
    update_id = body.get("update_id")
    message = body.get("message")
    if type(update_id) is not int or not isinstance(message, dict):
        _log_telegram_webhook_outcome("invalid_structure", update_id, started_at)
        return {"result": "OK"}

    message_date = message.get("date")
    sender = message.get("from")
    contact = message.get("contact")
    if not isinstance(contact, dict):
        _log_telegram_webhook_outcome("no_contact", update_id, started_at)
        return {"result": "OK"}
    if (
        type(message_date) is not int
        or not isinstance(sender, dict)
    ):
        _log_telegram_webhook_outcome("invalid_structure", update_id, started_at)
        return {"result": "OK"}

    sender_id = sender.get("id")
    contact_user_id = contact.get("user_id")
    if type(sender_id) is not int or type(contact_user_id) is not int:
        _log_telegram_webhook_outcome("invalid_structure", update_id, started_at)
        return {"result": "OK"}
    if sender_id != contact_user_id:
        _log_telegram_webhook_outcome("sender_contact_mismatch", update_id, started_at, sender_id)
        return {"result": "OK"}

    try:
        message_at = datetime.datetime.fromtimestamp(message_date, tz=datetime.UTC)
        canonical_phone = normalize_phone_number(contact.get("phone_number"))
    except (InvalidPhoneNumber, OverflowError, OSError, ValueError):
        _log_telegram_webhook_outcome("invalid_contact", update_id, started_at, sender_id)
        return {"result": "OK"}

    async with async_session() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == sender_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            _log_telegram_webhook_outcome("user_not_found", update_id, started_at, sender_id)
            return {"result": "OK"}
        if not is_newer_contact_update(user, message_at, update_id):
            _log_telegram_webhook_outcome("stale_or_replay", update_id, started_at, sender_id)
            return {"result": "OK"}

        user.phone_number = canonical_phone
        user.phone_verified_at = datetime.datetime.now(datetime.UTC)
        user.phone_verified_fingerprint = phone_verification_fingerprint(
            sender_id, canonical_phone
        )
        user.phone_verified_message_at = message_at
        user.phone_verified_update_id = update_id
        await db.commit()

    _log_telegram_webhook_outcome("phone_saved", update_id, started_at, sender_id)

    return {"result": "OK"}


@router.post("/order-status")
async def order_status_webhook(
    request: Request,
    clientid: str | None = Header(None, alias="clientId"),
    clientsecret: str | None = Header(None, alias="clientSecret"),
) -> dict:
    """Receive order status updates from AliPOS."""
    _verify_webhook_credentials(clientid, clientsecret)

    body = await request.json()
    eats_id = body.get("eatsId")
    new_status = body.get("status")
    order_number = body.get("orderNumber")
    provider_updated_at = parse_alipos_updated_at(body.get("updatedAt"))

    if not eats_id or not new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing eatsId or status"
        )

    async with async_session() as db:
        result = await db.execute(select(Order).where(Order.alipos_eats_id == eats_id))
        order = result.scalar_one_or_none()
        if order and await apply_alipos_status_update_for_order(
            db,
            order,
            new_status,
            order_number,
            provider_updated_at=provider_updated_at,
        ):
            await db.commit()

    return {"result": "OK"}


@router.post("/multicard/callback")
async def multicard_callback(
    request: Request, background_tasks: BackgroundTasks
) -> dict:
    """Receive successful payment callback from Multicard.

    Multicard POSTs here after a successful hosted-checkout payment.
    We verify the MD5 signature, find the order, and mark it as paid.
    Multicard treats an empty HTTP 200 response as acceptance. Rejected callbacks
    intentionally return non-2xx so a malformed or mismatched payment is not
    acknowledged as successfully processed.
    """
    body = await request.json()

    store_id = body.get("store_id")
    invoice_id = body.get("invoice_id")  # We set this to str(order.id)
    amount = body.get("amount")
    sign = body.get("sign")

    if not all([store_id is not None, invoice_id, amount is not None, sign]):
        logger.warning(
            "Multicard callback missing required fields: %s", list(body.keys())
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required payment callback fields",
        )

    try:
        parsed_store_id = int(store_id)
        parsed_amount = int(amount)
    except (TypeError, ValueError):
        logger.warning("Multicard callback has invalid numeric fields")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment callback fields",
        ) from None

    if parsed_store_id != settings.multicard_store_id:
        logger.warning(
            "Multicard callback store mismatch for invoice_id=%s",
            invoice_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment store does not match",
        )

    if not multicard_api.verify_callback_signature(
        store_id=parsed_store_id,
        invoice_id=str(invoice_id),
        amount=parsed_amount,
        received_sign=str(sign),
    ):
        logger.warning(
            "Multicard callback invalid signature for invoice_id=%s store_id=%s amount=%s",
            invoice_id,
            store_id,
            amount,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment callback signature",
        )

    # Parse order ID from invoice_id
    try:
        order_uuid = uuid.UUID(str(invoice_id))
    except ValueError:
        logger.warning(
            "Multicard callback: cannot parse invoice_id as UUID: %s", invoice_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invoice identifier",
        ) from None

    payment_uuid = body.get("uuid")
    receipt_url = body.get("receipt_url")
    card_pan = body.get("card_pan")
    ps = body.get("ps")

    async with async_session() as db:
        result = await db.execute(
            select(Order).where(Order.id == order_uuid).with_for_update()
        )
        order = result.scalar_one_or_none()

        if not order:
            logger.warning(
                "Multicard callback: order not found for invoice_id=%s", invoice_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        if not payment_uuid:
            logger.warning(
                "Multicard callback missing payment UUID for order=%s", order_uuid
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing payment identifier",
            )

        expected_amount = int(order.total_amount * 100)
        if parsed_amount != expected_amount:
            logger.warning(
                "Multicard callback amount mismatch for order=%s",
                order_uuid,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount does not match order",
            )

        processed_payment_states = {
            "paid",
            "refund_pending",
            "refunded",
            "refund_failed",
        }
        if order.payment_status in processed_payment_states:
            if order.multicard_payment_uuid != str(payment_uuid):
                logger.warning(
                    "Multicard callback payment mismatch for processed order=%s",
                    order_uuid,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment identifier does not match order",
                )
            logger.info(
                "Multicard callback: order %s already processed, skipping",
                order_uuid,
            )
            return {}

        known_provider_references = {
            str(reference)
            for reference in (
                order.multicard_invoice_uuid,
                order.multicard_payment_uuid,
            )
            if reference
        }
        if known_provider_references and str(payment_uuid) not in known_provider_references:
            logger.warning(
                "Multicard callback payment mismatch for order=%s",
                order_uuid,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Payment identifier does not match order",
            )

        legacy_paid_delivery = (
            order.discriminator == "delivery"
            and order.payment_method == "rahmat"
            and order.payment_provider == "multicard"
            and order.payment_status == "pending"
            and order.alipos_order_id is not None
            and order.multicard_invoice_uuid is not None
            and order.alipos_sync_status in {None, "synced"}
        )
        valid_payment_state = (
            order.payment_method == "rahmat"
            and order.payment_provider == "multicard"
            and order.alipos_order_id is None
            and (
                (
                    order.status == "AWAITING_PAYMENT"
                    and order.payment_status == "pending"
                )
                or (
                    order.status == "PAYMENT_REVIEW"
                    and order.payment_status
                    in {"invoice_queued", "invoice_sending", "invoice_unknown"}
                )
            )
        )
        if not valid_payment_state and not legacy_paid_delivery:
            logger.warning(
                "Multicard callback order is not awaiting online payment: order=%s",
                order_uuid,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order is not awaiting online payment",
            )

        order.payment_provider = "multicard"
        order.payment_status = "paid"
        order.invoice_cancel_status = "paid"
        order.payment_paid_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        order.multicard_payment_uuid = str(payment_uuid)
        order.multicard_receipt_url = str(receipt_url) if receipt_url else None
        order.payment_card_pan = str(card_pan) if card_pan else None
        order.payment_ps = str(ps) if ps else None
        order.payment_error = None
        if legacy_paid_delivery:
            order.alipos_sync_status = "synced"
            order.alipos_sync_error = None
        else:
            order.alipos_sync_status = "queued"
            order.alipos_sync_error = None
            order.status = "PAID_AWAITING_RESTAURANT"

        await db.commit()

    if not legacy_paid_delivery:
        background_tasks.add_task(dispatch_queued_alipos_order, order_uuid)

    logger.info(
        "Multicard payment confirmed: order=%s amount=%s ps=%s",
        order_uuid,
        amount,
        ps,
    )

    return {}


@router.post("/stoplist/{product_id}")
async def stoplist_webhook(
    product_id: uuid.UUID,
    restaurantId: str,
    count: int,
    clientid: str | None = Header(None, alias="clientId"),
    clientsecret: str | None = Header(None, alias="clientSecret"),
) -> dict:
    """Receive stop-list updates from AliPOS."""
    _verify_webhook_credentials(clientid, clientsecret)

    restaurant_uuid = uuid.UUID(restaurantId)

    async with async_session() as db:
        result = await db.execute(
            select(Stoplist).where(
                Stoplist.product_id == product_id,
                Stoplist.restaurant_id == restaurant_uuid,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.count = count
            entry.updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        else:
            db.add(
                Stoplist(
                    product_id=product_id,
                    restaurant_id=restaurant_uuid,
                    count=count,
                )
            )
        await db.commit()

    return {"result": "OK"}
