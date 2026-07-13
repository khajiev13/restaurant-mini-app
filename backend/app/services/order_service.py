import asyncio
import datetime
import logging
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
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


class PaymentRetryConflict(RuntimeError):
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


def _alipos_integration_total(order: Order) -> Decimal:
    if order.discriminator == "inplace":
        return Decimal(str(order.items_cost))
    return Decimal(str(order.total_amount))


def _alipos_log_fields(order: Order) -> dict[str, object]:
    return {
        "local_order_id": str(order.id),
        "discriminator": order.discriminator,
        "payment_kind": "cash" if order.payment_method == "cash" else "online",
        "items_cost": float(order.items_cost),
        "payable_total": float(order.total_amount),
        "integration_total": float(_alipos_integration_total(order)),
        "service_percent": float(order.service_percent or 0),
    }


def _queue_paid_submission_refund(order: Order) -> bool:
    if order.payment_status != "paid" or order.refund_sync_status is not None:
        return False
    order.payment_status = "refund_pending"
    order.refund_sync_status = "queued"
    order.refund_sync_error = None
    return True


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
            "total": float(_alipos_integration_total(order)),
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
        should_refund = _queue_paid_submission_refund(order)
        await db.commit()
        logger.warning("alipos_submit_rejected", extra=_alipos_log_fields(order))
        if should_refund:
            await _dispatch_queued_refund(db, order.id)
        raise OrderSubmissionRejected(str(exc)) from exc

    order.alipos_sync_status = "sending"
    order.alipos_sync_error = None
    await db.commit()
    logger.info("alipos_submit_start", extra=_alipos_log_fields(order))

    try:
        response = await alipos_api.create_order(payload)
    except alipos_api.AliPOSRejected as exc:
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = str(exc)
        order.status = "SUBMISSION_FAILED"
        should_refund = _queue_paid_submission_refund(order)
        await db.commit()
        logger.warning(
            "alipos_submit_rejected",
            extra={**_alipos_log_fields(order), "http_status": exc.status_code},
        )
        if should_refund:
            await _dispatch_queued_refund(db, order.id)
        raise OrderSubmissionRejected(str(exc)) from exc
    except Exception:
        order.alipos_sync_status = "unknown"
        order.alipos_sync_error = "AliPOS order create outcome is unknown"
        order.status = "SYNC_UNKNOWN"
        await db.commit()
        logger.warning("alipos_submit_unknown", extra=_alipos_log_fields(order))
        return

    alipos_order_id = response.get("orderId")
    try:
        order.alipos_order_id = uuid.UUID(str(alipos_order_id))
    except (TypeError, ValueError) as exc:
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = "AliPOS response did not include a valid orderId"
        order.status = "SUBMISSION_FAILED"
        should_refund = _queue_paid_submission_refund(order)
        await db.commit()
        logger.warning("alipos_submit_rejected", extra=_alipos_log_fields(order))
        if should_refund:
            await _dispatch_queued_refund(db, order.id)
        raise OrderSubmissionRejected(order.alipos_sync_error) from exc
    order.alipos_sync_status = "synced"
    order.alipos_sync_error = None
    order.status = "NEW"
    await db.commit()
    logger.info("alipos_submit_synced", extra=_alipos_log_fields(order))


def _ready_for_alipos_clause():
    return or_(Order.payment_method == "cash", Order.payment_status == "paid")


async def list_recoverable_alipos_order_ids(db: AsyncSession) -> list[uuid.UUID]:
    result = await db.execute(
        select(Order.id).where(
            Order.alipos_sync_status == "queued",
            _ready_for_alipos_clause(),
        )
    )
    return list(result.scalars())


async def recover_interrupted_alipos_orders(db: AsyncSession) -> int:
    """Mark interrupted create attempts unknown without repeating the mutation."""
    result = await db.execute(
        select(Order)
        .where(
            Order.alipos_sync_status == "sending",
            Order.alipos_order_id.is_(None),
        )
        .with_for_update(skip_locked=True)
    )
    interrupted = list(result.scalars())
    for order in interrupted:
        order.alipos_sync_status = "unknown"
        order.alipos_sync_error = "AliPOS order create outcome is unknown"
        order.status = "SYNC_UNKNOWN"
        logger.warning("alipos_submit_unknown", extra=_alipos_log_fields(order))
    await db.commit()
    return len(interrupted)


async def _submit_queued_alipos_order(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> Order | None:
    """Atomically claim a never-attempted cash or paid order and submit it once."""
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.alipos_sync_status == "queued",
            _ready_for_alipos_clause(),
        )
        .with_for_update(skip_locked=True)
    )
    order = result.scalar_one_or_none()
    if order is None:
        return None
    order.alipos_sync_status = "sending"
    await db.commit()
    await submit_order_to_alipos(db, order)
    return order


async def dispatch_queued_alipos_order(order_id: uuid.UUID) -> None:
    """Claim one never-attempted cash or paid order for one AliPOS create attempt."""
    async with async_session() as db:
        try:
            await _submit_queued_alipos_order(db, order_id)
        except OrderSubmissionRejected:
            logger.exception("AliPOS rejected queued local order %s", order_id)


async def recover_queued_alipos_orders() -> None:
    """Schedule only never-attempted cash or paid orders after a restart."""
    async with async_session() as db:
        await recover_interrupted_alipos_orders(db)
        order_ids = await list_recoverable_alipos_order_ids(db)
    for order_id in order_ids:
        asyncio.create_task(dispatch_queued_alipos_order(order_id))


async def list_recoverable_refund_order_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Return refunds that were durably queued but never attempted."""
    result = await db.execute(
        select(Order.id).where(
            Order.payment_status == "refund_pending",
            Order.refund_sync_status == "queued",
        )
    )
    return list(result.scalars())


async def _dispatch_queued_refund(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    """Claim and attempt one never-attempted refund.

    Transport failures are deliberately recorded as unknown: retrying DELETE after
    a timeout could refund twice if the provider processed the first request.
    """
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.payment_status == "refund_pending",
            Order.refund_sync_status == "queued",
        )
        .with_for_update(skip_locked=True)
    )
    order = result.scalar_one_or_none()
    if order is None:
        return None
    if not order.multicard_payment_uuid:
        order.payment_status = "refund_failed"
        order.refund_sync_status = "failed"
        order.refund_sync_error = "Missing payment reference"
        order.payment_error = "The online refund needs staff assistance"
        await db.commit()
        return order

    order.refund_sync_status = "sending"
    order.refund_sync_error = None
    await db.commit()
    try:
        await multicard_api.refund_payment(order.multicard_payment_uuid)
    except httpx.RequestError:
        logger.exception("Multicard refund outcome unknown for local order %s", order.id)
        order.refund_sync_status = "unknown"
        order.refund_sync_error = "Provider refund outcome is unknown"
        order.payment_error = "The refund is being verified"
    except Exception:
        logger.exception("Multicard refund rejected for local order %s", order.id)
        order.payment_status = "refund_failed"
        order.refund_sync_status = "failed"
        order.refund_sync_error = "Provider rejected the refund request"
        order.payment_error = "The online refund needs staff assistance"
    else:
        order.payment_status = "refunded"
        order.refund_sync_status = "refunded"
        order.refund_sync_error = None
        order.payment_error = None
    await db.commit()
    return order


async def dispatch_queued_refund(order_id: uuid.UUID) -> None:
    async with async_session() as db:
        await _dispatch_queued_refund(db, order_id)


async def reconcile_unknown_refunds(db: AsyncSession) -> int:
    """Confirm completed refunds after a timeout or process interruption.

    Non-refunded provider states remain unknown for staff review; this function
    never repeats a potentially completed refund request.
    """
    result = await db.execute(
        select(Order).where(
            Order.payment_status == "refund_pending",
            Order.refund_sync_status.in_(["sending", "unknown"]),
            Order.multicard_payment_uuid.is_not(None),
        )
    )
    reconciled = 0
    for order in result.scalars():
        try:
            payment = await multicard_api.get_payment(order.multicard_payment_uuid)
        except Exception:
            order.refund_sync_status = "unknown"
            order.refund_sync_error = "Could not verify provider refund state"
            continue
        provider_status = str(
            payment.get("status") or payment.get("payment_status") or ""
        ).casefold()
        if provider_status in {"revert", "reverted", "refunded", "refund"}:
            order.payment_status = "refunded"
            order.refund_sync_status = "refunded"
            order.refund_sync_error = None
            order.payment_error = None
            reconciled += 1
        else:
            order.refund_sync_status = "unknown"
            order.refund_sync_error = "Provider does not report a completed refund"
    await db.commit()
    return reconciled


async def recover_refund_operations() -> None:
    """Resume safe queued refunds and reconcile ambiguous attempts on startup."""
    async with async_session() as db:
        order_ids = await list_recoverable_refund_order_ids(db)
        await reconcile_unknown_refunds(db)
    for order_id in order_ids:
        asyncio.create_task(dispatch_queued_refund(order_id))


async def expire_due_payment_orders(
    db: AsyncSession,
    now: datetime.datetime,
) -> int:
    """Expire only invoices whose cancellation Multicard confirms while row-locked."""
    result = await db.execute(
        select(Order)
        .where(
            Order.payment_status == "pending",
            Order.payment_expires_at.is_not(None),
            Order.payment_expires_at <= now,
            Order.alipos_order_id.is_(None),
        )
        .with_for_update(skip_locked=True)
    )
    expired_count = 0
    for order in result.scalars():
        if not order.multicard_invoice_uuid:
            logger.error("Expired order %s has no cancellable invoice UUID", order.id)
            continue
        try:
            await multicard_api.cancel_invoice_strict(order.multicard_invoice_uuid)
        except Exception:
            logger.warning(
                "Invoice cancellation was not confirmed for expired order %s",
                order.id,
            )
            continue
        order.payment_status = "expired"
        order.status = "CANCELLED"
        order.payment_error = "Payment timeout — invoice cancellation confirmed"
        expired_count += 1
    await db.commit()
    return expired_count


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
        order.refund_sync_status = "queued"
        order.refund_sync_error = None
    await db.commit()

    if not should_refund:
        return order
    refunded = await _dispatch_queued_refund(db, order.id)
    return refunded or order


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
    if order.payment_method != "rahmat" or order.alipos_order_id is not None:
        raise PaymentSwitchConflict("This order can no longer switch to cash")
    pending_invoice = (
        order.payment_status == "pending"
        and order.status == "AWAITING_PAYMENT"
        and order.alipos_sync_status == "awaiting_payment"
    )
    definitively_inactive = (
        (order.payment_status == "failed" and order.status == "PAYMENT_FAILED")
        or (order.payment_status == "expired" and order.status == "CANCELLED")
    )
    if not pending_invoice and not definitively_inactive:
        raise PaymentSwitchConflict("This order can no longer switch to cash")
    if pending_invoice:
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

    submitted = await _submit_queued_alipos_order(db, order.id)
    return submitted or order


async def _create_order_invoice(db: AsyncSession, order: Order) -> Order:
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.payment_status = "pending"
    order.payment_expires_at = now + datetime.timedelta(
        seconds=settings.rahmat_payment_timeout_seconds
    )
    order.payment_error = None
    order.multicard_invoice_uuid = None
    order.multicard_checkout_url = None
    order.alipos_sync_status = "awaiting_payment"
    order.status = "AWAITING_PAYMENT"
    await db.commit()
    try:
        invoice = await multicard_api.create_invoice(
            amount_tiyin=int(order.total_amount * 100),
            invoice_id=str(order.id),
            return_url=settings.telegram_order_deep_link(str(order.id)),
            ttl=settings.rahmat_payment_timeout_seconds,
        )
        order.multicard_invoice_uuid = invoice.get("uuid")
        order.multicard_checkout_url = invoice["checkout_url"]
    except httpx.RequestError:
        order.payment_status = "invoice_unknown"
        order.payment_error = "The payment link outcome needs verification"
        order.status = "PAYMENT_REVIEW"
    except Exception:
        order.payment_status = "failed"
        order.payment_error = "Could not create the online payment"
        order.status = "PAYMENT_FAILED"
    await db.commit()
    return order


async def retry_customer_order_payment(
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
    can_retry = (
        order.discriminator == "inplace"
        and order.payment_method == "rahmat"
        and order.alipos_order_id is None
        and (
            (order.payment_status == "failed" and order.status == "PAYMENT_FAILED")
            or (order.payment_status == "expired" and order.status == "CANCELLED")
        )
    )
    if not can_retry:
        raise PaymentRetryConflict("This online payment cannot be retried safely")
    return await _create_order_invoice(db, order)


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
    if body.client_request_id:
        result = await db.execute(
            select(Order).where(
                Order.user_id == current_user.telegram_id,
                Order.client_request_id == body.client_request_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.alipos_sync_status == "queued":
                submitted = await _submit_queued_alipos_order(db, existing.id)
                if submitted is not None:
                    return submitted
                await db.refresh(existing)
            return existing

    selected_address = None
    table = None
    delivery_address = None
    if body.discriminator == "delivery":
        selected_address, delivery_address = await _resolve_delivery(
            db, current_user, body
        )
    else:
        table_token = body.table_access_token or ""
        table_claims = table_access.verify_access_token(table_token)
        table = await table_access.resolve_access_token(table_token)

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
        client_request_id=body.client_request_id,
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
        table_access_expires_at=(
            table_claims.expires_at.astimezone(datetime.UTC).replace(tzinfo=None)
            if table
            else None
        ),
        alipos_eats_id=f"mrpub-{uuid.uuid4().hex[:12]}",
        alipos_sync_status="awaiting_payment" if online else "queued",
        status="AWAITING_PAYMENT" if online else "NEW",
    )
    db.add(order)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if not body.client_request_id:
            raise
        result = await db.execute(
            select(Order).where(
                Order.user_id == current_user.telegram_id,
                Order.client_request_id == body.client_request_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise
        if existing.alipos_sync_status == "queued":
            submitted = await _submit_queued_alipos_order(db, existing.id)
            if submitted is not None:
                return submitted
            await db.refresh(existing)
        return existing
    await db.refresh(order)

    if not online:
        submitted = await _submit_queued_alipos_order(db, order.id)
        return submitted or order

    return await _create_order_invoice(db, order)
