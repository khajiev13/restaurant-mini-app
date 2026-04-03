import datetime
import hmac
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.models import Order, Stoplist, User
from app.services import multicard_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_webhook_credentials(client_id: str | None, client_secret: str | None) -> None:
    """Verify that AliPOS webhook headers match our credentials."""
    import hmac as _hmac

    if not client_id or not client_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")

    id_ok = _hmac.compare_digest(client_id, settings.alipos_api_client_id)
    secret_ok = _hmac.compare_digest(client_secret, settings.alipos_api_client_secret)
    if not id_ok or not secret_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


@router.post("/bot")
async def telegram_bot_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict:
    """Receive Telegram bot updates (contact messages)."""
    if settings.telegram_webhook_secret:
        if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")

    body = await request.json()
    message = body.get("message", {})
    contact = message.get("contact")
    if not contact:
        return {"result": "OK"}

    telegram_id = contact.get("user_id") or (message.get("from") or {}).get("id")
    phone_number = contact.get("phone_number")

    if not telegram_id or not phone_number:
        return {"result": "OK"}

    async with async_session() as db:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.phone_number = phone_number
            await db.commit()

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing eatsId or status")

    async with async_session() as db:
        result = await db.execute(
            select(Order).where(Order.alipos_eats_id == eats_id)
        )
        order = result.scalar_one_or_none()
        if order:
            order.status = new_status
            order.order_number = order_number
            order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            await db.commit()

    return {"result": "OK"}


@router.post("/multicard/callback")
async def multicard_callback(request: Request) -> dict:
    """Receive successful payment callback from Multicard.

    Multicard POSTs here after a successful hosted-checkout payment.
    We verify the MD5 signature, find the order, and mark it as paid.
    Must respond HTTP 200 with {"success": true} — any other response triggers payment reversal.
    """
    body = await request.json()

    store_id = body.get("store_id")
    invoice_id = body.get("invoice_id")  # We set this to str(order.id)
    amount = body.get("amount")
    sign = body.get("sign")

    if not all([store_id is not None, invoice_id, amount is not None, sign]):
        logger.warning("Multicard callback missing required fields: %s", list(body.keys()))
        # Return 200 with success:true — we don't want Multicard to reverse the payment
        return {"success": True}

    # Verify signature
    if not multicard_api.verify_callback_signature(
        store_id=int(store_id),
        invoice_id=str(invoice_id),
        amount=int(amount),
        received_sign=str(sign),
    ):
        logger.warning(
            "Multicard callback invalid signature for invoice_id=%s store_id=%s amount=%s",
            invoice_id,
            store_id,
            amount,
        )
        # Return 200 with success:true to avoid payment reversal — log for investigation
        return {"success": True}

    # Parse order ID from invoice_id
    try:
        order_uuid = uuid.UUID(str(invoice_id))
    except ValueError:
        logger.warning("Multicard callback: cannot parse invoice_id as UUID: %s", invoice_id)
        return {"success": True}

    payment_uuid = body.get("uuid")
    receipt_url = body.get("receipt_url")
    card_pan = body.get("card_pan")
    ps = body.get("ps")

    async with async_session() as db:
        result = await db.execute(select(Order).where(Order.id == order_uuid))
        order = result.scalar_one_or_none()

        if not order:
            logger.warning("Multicard callback: order not found for invoice_id=%s", invoice_id)
            return {"success": True}

        # Idempotency: already processed
        if order.payment_status == "paid":
            logger.info("Multicard callback: order %s already paid, skipping", order_uuid)
            return {"success": True}

        order.payment_provider = "multicard"
        order.payment_status = "paid"
        order.payment_paid_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        order.multicard_payment_uuid = str(payment_uuid) if payment_uuid else None
        order.multicard_receipt_url = str(receipt_url) if receipt_url else None
        order.payment_card_pan = str(card_pan) if card_pan else None
        order.payment_ps = str(ps) if ps else None

        await db.commit()

    logger.info(
        "Multicard payment confirmed: order=%s amount=%s ps=%s card_pan=%s",
        order_uuid,
        amount,
        ps,
        card_pan,
    )

    return {"success": True}


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
