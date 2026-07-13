import asyncio
import datetime
import logging
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.models import Address, Order, User
from app.schemas.order import OrderCreate
from app.services import alipos_api, multicard_api
from app.services.menu_catalog_service import price_cart
from app.services.order_status_service import normalize_order_status
from app.services.table_access_service import TableAccessService

logger = logging.getLogger(__name__)

table_access = TableAccessService(
    secret=settings.effective_table_access_secret,
    bot_username=settings.telegram_bot_username,
    access_ttl_seconds=settings.table_access_ttl_seconds,
)


class CustomerOrderError(ValueError):
    pass


class PaymentMethodUnavailable(RuntimeError):
    pass


class OrderSubmissionRejected(RuntimeError):
    pass


class PaymentCheckoutError(RuntimeError):
    pass


class CustomerOrderNotFound(LookupError):
    pass


class CancellationConflict(RuntimeError):
    pass


class CancellationError(RuntimeError):
    pass


class PaymentSwitchConflict(RuntimeError):
    pass


class PaymentSwitchError(RuntimeError):
    pass


def _normalize_payment_title(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


async def resolve_payment_method_id(kind: Literal["cash", "online"]) -> str:
    methods = await alipos_api.get_payment_methods()
    configured_id = (
        settings.alipos_cash_payment_id
        if kind == "cash"
        else settings.alipos_online_order_payment_id
    )
    if configured_id:
        configured = next(
            (
                method
                for method in methods
                if str(method.get("id", "")).casefold() == configured_id.casefold()
            ),
            None,
        )
        if configured:
            return str(configured["id"])

    accepted_titles = (
        {"cash", "наличные", "naqd", "naqd pul"}
        if kind == "cash"
        else {"online order", "online", "rahmat"}
    )
    match = next(
        (
            method
            for method in methods
            if _normalize_payment_title(str(method.get("title", ""))) in accepted_titles
        ),
        None,
    )
    if match is None:
        raise PaymentMethodUnavailable(f"AliPOS {kind} payment method is unavailable")
    return str(match["id"])


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _alipos_items(items: list[dict]) -> list[dict]:
    return [
        {
            "id": item["id"],
            "quantity": item["quantity"],
            "price": item["price"],
            "modifications": [
                {
                    "id": modifier["id"],
                    "quantity": modifier["quantity"],
                    "price": modifier["price"],
                }
                for modifier in item.get("modifications", [])
            ],
        }
        for item in items
    ]


async def _build_alipos_payload(order: Order) -> dict:
    payment_kind: Literal["cash", "online"] = (
        "cash" if order.payment_method == "cash" else "online"
    )
    payment_id = await resolve_payment_method_id(payment_kind)
    payload = {
        "discriminator": order.discriminator,
        "platform": "MrPubBot",
        "eatsId": order.alipos_eats_id,
        "restaurantId": settings.alipos_restaurant_id,
        "comment": order.comment or "",
        "deliveryInfo": order.delivery_info or {},
        "paymentInfo": {
            "paymentId": payment_id,
            "itemsCost": float(order.items_cost),
            "total": float(order.total_amount),
            "deliveryFee": float(order.delivery_fee),
        },
        "items": _alipos_items(order.items),
    }
    if order.discriminator == "inplace":
        payload["tableId"] = str(order.table_id)
    return payload


async def submit_order_to_alipos(db: AsyncSession, order: Order) -> None:
    try:
        payload = await _build_alipos_payload(order)
    except Exception as exc:
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = str(exc)
        order.status = "SUBMISSION_FAILED"
        await db.commit()
        raise OrderSubmissionRejected(str(exc)) from exc

    order.alipos_sync_status = "sending"
    order.alipos_sync_error = None
    await db.commit()

    try:
        response = await alipos_api.create_order(payload)
    except alipos_api.AliPOSRejected as exc:
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = str(exc)
        order.status = "SUBMISSION_FAILED"
        await db.commit()
        raise OrderSubmissionRejected(str(exc)) from exc
    except Exception:
        logger.exception("AliPOS order outcome unknown for local order %s", order.id)
        order.alipos_sync_status = "unknown"
        order.alipos_sync_error = "AliPOS order create outcome is unknown"
        order.status = "SYNC_UNKNOWN"
        await db.commit()
        return

    alipos_order_id = response.get("orderId")
    try:
        order.alipos_order_id = uuid.UUID(str(alipos_order_id))
    except (TypeError, ValueError) as exc:
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = "AliPOS response did not include a valid orderId"
        order.status = "SUBMISSION_FAILED"
        await db.commit()
        raise OrderSubmissionRejected(order.alipos_sync_error) from exc
    order.alipos_sync_status = "synced"
    order.alipos_sync_error = None
    order.status = "NEW"
    await db.commit()


async def dispatch_queued_alipos_order(order_id: uuid.UUID) -> None:
    """Claim one paid order for a single AliPOS create attempt."""
    async with async_session() as db:
        result = await db.execute(
            select(Order)
            .where(
                Order.id == order_id,
                Order.alipos_sync_status == "queued",
                Order.payment_status == "paid",
            )
            .with_for_update(skip_locked=True)
        )
        order = result.scalar_one_or_none()
        if order is None:
            return
        order.alipos_sync_status = "sending"
        await db.commit()
        try:
            await submit_order_to_alipos(db, order)
        except OrderSubmissionRejected:
            logger.exception("AliPOS rejected paid local order %s", order_id)


async def recover_queued_alipos_orders() -> None:
    """Schedule only never-attempted paid orders after a process restart."""
    async with async_session() as db:
        result = await db.execute(
            select(Order.id).where(
                Order.alipos_sync_status == "queued",
                Order.payment_status == "paid",
            )
        )
        order_ids = list(result.scalars())
    for order_id in order_ids:
        asyncio.create_task(dispatch_queued_alipos_order(order_id))


async def cancel_customer_order(
    db: AsyncSession,
    current_user: User,
    order_id: uuid.UUID,
) -> Order:
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
        )
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise CustomerOrderNotFound("Order not found")
    if order.discriminator != "inplace":
        raise CancellationConflict("Only table orders can be cancelled here")

    if (
        order.status == "AWAITING_PAYMENT"
        and order.payment_status == "pending"
        and order.alipos_order_id is None
    ):
        if not order.multicard_invoice_uuid:
            raise CancellationConflict(
                "The online invoice cannot be safely cancelled; please ask staff"
            )
        try:
            await multicard_api.cancel_invoice_strict(order.multicard_invoice_uuid)
        except Exception as exc:
            raise CancellationError(
                "Could not confirm that the online payment was cancelled"
            ) from exc
        order.status = "CANCELLED"
        order.payment_status = "cancelled"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await db.commit()
        return order

    if order.alipos_order_id is None or order.alipos_sync_status != "synced":
        raise CancellationConflict(
            "This order cannot be safely cancelled automatically; please ask staff"
        )

    try:
        current = await alipos_api.get_order_status(str(order.alipos_order_id))
    except Exception as exc:
        raise CancellationError("Could not verify the restaurant order status") from exc
    current_status = normalize_order_status(str(current.get("status") or ""))
    if current_status != "NEW":
        if current_status:
            order.status = current_status
            order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(
                tzinfo=None
            )
            await db.commit()
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )

    order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    try:
        await alipos_api.cancel_order(
            str(order.alipos_order_id),
            "Mijoz yangi buyurtmani bekor qildi",
        )
    except Exception as exc:
        order.alipos_cancel_status = "unknown"
        order.alipos_cancel_error = "AliPOS cancellation outcome is unknown"
        await db.commit()
        raise CancellationError(
            "The cancellation result could not be confirmed"
        ) from exc

    order.status = "CANCELLED"
    order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.alipos_cancel_status = "cancelled"
    order.alipos_cancel_error = None
    should_refund = order.payment_status == "paid"
    if should_refund:
        order.payment_status = "refund_pending"
    await db.commit()

    if not should_refund:
        return order
    if not order.multicard_payment_uuid:
        order.payment_status = "refund_failed"
        order.payment_error = "Missing Multicard payment reference"
        await db.commit()
        return order
    try:
        await multicard_api.refund_payment(order.multicard_payment_uuid)
    except Exception:
        logger.exception("Multicard refund failed for local order %s", order.id)
        order.payment_status = "refund_failed"
        order.payment_error = "The online refund could not be completed"
    else:
        order.payment_status = "refunded"
        order.payment_error = None
    await db.commit()
    return order


async def switch_customer_order_to_cash(
    db: AsyncSession,
    current_user: User,
    order_id: uuid.UUID,
) -> Order:
    """Safely invalidate an unpaid invoice before submitting the order as cash."""
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
        )
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise CustomerOrderNotFound("Order not found")
    if order.discriminator != "inplace":
        raise PaymentSwitchConflict("Only table orders can switch to cash here")
    if not (
        order.payment_method == "rahmat"
        and order.payment_status == "pending"
        and order.status == "AWAITING_PAYMENT"
        and order.alipos_order_id is None
        and order.alipos_sync_status == "awaiting_payment"
    ):
        raise PaymentSwitchConflict("This order can no longer switch to cash")
    if not order.multicard_invoice_uuid:
        raise PaymentSwitchConflict(
            "The online invoice cannot be safely cancelled; please ask staff"
        )

    try:
        await multicard_api.cancel_invoice_strict(order.multicard_invoice_uuid)
    except Exception as exc:
        raise PaymentSwitchError(
            "Could not confirm that the online payment was cancelled"
        ) from exc

    order.payment_method = "cash"
    order.payment_provider = None
    order.payment_status = None
    order.payment_expires_at = None
    order.payment_error = None
    order.multicard_checkout_url = None
    order.alipos_sync_status = "queued"
    order.alipos_sync_error = None
    order.status = "NEW"
    await db.commit()

    await submit_order_to_alipos(db, order)
    return order


async def _resolve_delivery(
    db: AsyncSession,
    current_user: User,
    body: OrderCreate,
) -> tuple[Address | None, dict]:
    selected_address = None
    delivery_address = body.delivery_address
    latitude = body.latitude
    longitude = body.longitude
    if body.address_id:
        result = await db.execute(
            select(Address).where(
                Address.id == body.address_id,
                Address.user_id == current_user.telegram_id,
            )
        )
        selected_address = result.scalar_one_or_none()
        if selected_address is None:
            raise CustomerOrderError("Delivery address not found")
        delivery_address = selected_address.full_address
        latitude = selected_address.latitude or latitude
        longitude = selected_address.longitude or longitude

    if not delivery_address:
        raise CustomerOrderError("Delivery address is required")
    if not latitude or not longitude:
        raise CustomerOrderError(
            "Selected delivery address is missing map coordinates. "
            "Edit the address and use your location before placing the order."
        )
    return selected_address, {
        "full": delivery_address,
        "latitude": latitude,
        "longitude": longitude,
    }


async def create_customer_order(
    db: AsyncSession,
    current_user: User,
    body: OrderCreate,
) -> Order:
    selected_address = None
    table = None
    delivery_address = None
    if body.discriminator == "delivery":
        selected_address, delivery_address = await _resolve_delivery(
            db, current_user, body
        )
    else:
        table = await table_access.resolve_access_token(body.table_access_token or "")

    priced = await price_cart(db, body.items)
    items_cost = _money(priced.items_cost)
    service_percent = table.service_percent if table else Decimal("0")
    service_charge = _money(items_cost * service_percent / Decimal("100"))
    delivery_fee = Decimal("0")
    total = _money(items_cost + service_charge + delivery_fee)
    order_id = uuid.uuid4()
    client_name = f"{current_user.first_name} {current_user.last_name or ''}".strip()
    delivery_info = {
        "clientName": client_name,
        "phoneNumber": body.phone_number,
    }
    if delivery_address:
        delivery_info["deliveryAddress"] = delivery_address

    online = body.payment_method == "rahmat"
    order = Order(
        id=order_id,
        user_id=current_user.telegram_id,
        address_id=selected_address.id if selected_address else body.address_id,
        items=priced.items,
        delivery_info=delivery_info,
        items_cost=items_cost,
        total_amount=total,
        delivery_fee=delivery_fee,
        comment=body.comment,
        payment_method=body.payment_method,
        payment_provider="multicard" if online else None,
        payment_status="pending" if online else None,
        discriminator=body.discriminator,
        table_id=table.table_id if table else None,
        table_title=table.table_title if table else None,
        hall_id=table.hall_id if table else None,
        hall_title=table.hall_title if table else None,
        service_percent=service_percent,
        alipos_eats_id=f"mrpub-{uuid.uuid4().hex[:12]}",
        alipos_sync_status="awaiting_payment" if online else "queued",
        status="AWAITING_PAYMENT" if online else "NEW",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    if not online:
        await submit_order_to_alipos(db, order)
        return order

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.payment_expires_at = now + datetime.timedelta(
        seconds=settings.rahmat_payment_timeout_seconds
    )
    try:
        invoice = await multicard_api.create_invoice(
            amount_tiyin=int(total * 100),
            invoice_id=str(order.id),
            return_url=settings.telegram_order_deep_link(str(order.id)),
            ttl=settings.rahmat_payment_timeout_seconds,
        )
        order.multicard_invoice_uuid = invoice.get("uuid")
        order.multicard_checkout_url = invoice["checkout_url"]
    except Exception as exc:
        order.payment_status = "failed"
        order.payment_error = "Could not create the online payment"
        order.status = "PAYMENT_FAILED"
        await db.commit()
        raise PaymentCheckoutError("Could not create the online payment") from exc
    await db.commit()
    return order
