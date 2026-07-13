import datetime
import hmac
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
from app.services.order_status_service import apply_alipos_status_update_for_order

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _mask_telegram_id(telegram_id: Any) -> str:
    value = str(telegram_id)
    if len(value) <= 4:
        return value
    return f"***{value[-4:]}"


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
    body = await request.json()
    update_id = body.get("update_id")
    message = body.get("message", {})
    contact = message.get("contact")

    logger.info(
        "Telegram bot webhook received | update_id=%s has_contact=%s",
        update_id,
        bool(contact),
    )

    if settings.telegram_webhook_secret:
        if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
        ):
            logger.warning(
                "Telegram bot webhook rejected | update_id=%s secret_valid=false duration_ms=%s",
                update_id,
                round((time.perf_counter() - started_at) * 1000),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret"
            )

        logger.info("Telegram bot webhook secret accepted | update_id=%s", update_id)

    if not contact:
        logger.info(
            "Telegram bot webhook ignored | update_id=%s result=no_contact duration_ms=%s",
            update_id,
            round((time.perf_counter() - started_at) * 1000),
        )
        return {"result": "OK"}

    telegram_id = contact.get("user_id") or (message.get("from") or {}).get("id")
    phone_number = contact.get("phone_number")

    if not telegram_id or not phone_number:
        logger.info(
            "Telegram bot webhook ignored | update_id=%s result=incomplete_contact telegram_user_id=%s duration_ms=%s",
            update_id,
            _mask_telegram_id(telegram_id or "unknown"),
            round((time.perf_counter() - started_at) * 1000),
        )
        return {"result": "OK"}

    async with async_session() as db:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.phone_number = phone_number
            await db.commit()
            logger.info(
                "Telegram bot webhook processed | update_id=%s result=phone_saved telegram_user_id=%s duration_ms=%s",
                update_id,
                _mask_telegram_id(telegram_id),
                round((time.perf_counter() - started_at) * 1000),
            )
        else:
            logger.info(
                "Telegram bot webhook ignored | update_id=%s result=user_not_found telegram_user_id=%s duration_ms=%s",
                update_id,
                _mask_telegram_id(telegram_id),
                round((time.perf_counter() - started_at) * 1000),
            )

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

        valid_payment_state = (
            order.payment_method == "rahmat"
            and order.status in {"AWAITING_PAYMENT", "PAYMENT_REVIEW"}
            and order.payment_status in {"pending", "invoice_unknown"}
        )
        if not valid_payment_state:
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
        order.payment_paid_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        order.multicard_payment_uuid = str(payment_uuid)
        order.multicard_receipt_url = str(receipt_url) if receipt_url else None
        order.payment_card_pan = str(card_pan) if card_pan else None
        order.payment_ps = str(ps) if ps else None
        order.payment_error = None
        order.alipos_sync_status = "queued"
        order.alipos_sync_error = None
        order.status = "PAID_AWAITING_RESTAURANT"

        await db.commit()

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
