import asyncio
import datetime
import logging
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import httpx
from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.models import Address, Order, User
from app.schemas.order import OrderCreate
from app.services import alipos_api, multicard_api
from app.services.menu_catalog_service import price_cart
from app.services.order_status_service import (
    TERMINAL_LOCAL_STATUSES,
    normalize_order_status,
)
from app.services.table_access_service import TableAccessService

logger = logging.getLogger(__name__)
ALIPOS_PAYLOAD_BUILD_ERROR = "AliPOS order payload could not be prepared"
ALIPOS_CANCEL_COMMENT = "Mijoz yangi buyurtmani bekor qildi"
ALIPOS_CANCEL_UNKNOWN_ERROR = "AliPOS cancellation outcome is unknown"
ALIPOS_CANCEL_RECONCILE_LIMIT = 5
ALIPOS_CANCEL_PENDING_STATUSES = (None, "not_started", "sending", "unknown")
ALIPOS_CANCELLABLE_LOCAL_STATUSES = ("NEW", "PAID_AWAITING_RESTAURANT")

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


def can_use_inplace_online_payment(user: User) -> bool:
    return (
        settings.inplace_online_payment_enabled
        or user.telegram_id in settings.inplace_online_payment_test_ids
    )


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


async def _finalize_alipos_attempt(
    db: AsyncSession,
    order: Order,
    *,
    sync_status: str,
    sync_error: str | None,
    local_status: str,
    alipos_order_id: uuid.UUID | None = None,
) -> bool:
    values: dict[str, object] = {
        "alipos_sync_status": sync_status,
        "alipos_sync_error": sync_error,
        "status": case(
            (
                Order.status.in_(("NEW", "PAID_AWAITING_RESTAURANT")),
                local_status,
            ),
            else_=Order.status,
        ),
    }
    if alipos_order_id is not None:
        values["alipos_order_id"] = alipos_order_id
    result = await db.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.alipos_sync_status == "sending",
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    await db.refresh(order)
    return result.rowcount > 0


async def submit_order_to_alipos(db: AsyncSession, order: Order) -> None:
    try:
        payload = await _build_alipos_payload(order)
    except Exception as exc:
        safe_error = (
            str(exc)
            if isinstance(
                exc,
                (PaymentMethodUnavailable, alipos_api.AliPOSPreSubmitError),
            )
            else ALIPOS_PAYLOAD_BUILD_ERROR
        )
        order.alipos_sync_status = "failed"
        order.alipos_sync_error = safe_error
        order.status = "SUBMISSION_FAILED"
        should_refund = _queue_paid_submission_refund(order)
        await db.commit()
        logger.warning("alipos_submit_rejected", extra=_alipos_log_fields(order))
        if should_refund:
            await _dispatch_queued_refund(db, order.id)
        raise OrderSubmissionRejected(safe_error) from None

    order.alipos_sync_status = "sending"
    order.alipos_sync_error = None
    await db.commit()
    logger.info("alipos_submit_start", extra=_alipos_log_fields(order))

    try:
        response = await alipos_api.create_order(payload)
    except (alipos_api.AliPOSRejected, alipos_api.AliPOSPreSubmitError) as exc:
        finalized = await _finalize_alipos_attempt(
            db,
            order,
            sync_status="failed",
            sync_error=str(exc),
            local_status="SUBMISSION_FAILED",
        )
        should_refund = finalized and _queue_paid_submission_refund(order)
        if should_refund:
            await db.commit()
        log_fields = _alipos_log_fields(order)
        if exc.status_code is not None:
            log_fields["http_status"] = exc.status_code
        logger.warning("alipos_submit_rejected", extra=log_fields)
        if should_refund:
            await _dispatch_queued_refund(db, order.id)
        raise OrderSubmissionRejected(str(exc)) from exc
    except Exception:
        await _finalize_alipos_attempt(
            db,
            order,
            sync_status="unknown",
            sync_error="AliPOS order create outcome is unknown",
            local_status="SYNC_UNKNOWN",
        )
        logger.warning("alipos_submit_unknown", extra=_alipos_log_fields(order))
        return

    try:
        alipos_order_id = response.get("orderId") if isinstance(response, dict) else None
        parsed_alipos_order_id = uuid.UUID(str(alipos_order_id))
    except (TypeError, ValueError):
        await _finalize_alipos_attempt(
            db,
            order,
            sync_status="unknown",
            sync_error="AliPOS order create outcome is unknown",
            local_status="SYNC_UNKNOWN",
        )
        logger.warning("alipos_submit_unknown", extra=_alipos_log_fields(order))
        return
    await _finalize_alipos_attempt(
        db,
        order,
        sync_status="synced",
        sync_error=None,
        local_status="NEW",
        alipos_order_id=parsed_alipos_order_id,
    )
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
            logger.warning(
                "alipos_dispatch_rejected",
                extra={"local_order_id": str(order_id)},
            )


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
    except multicard_api.RefundRejected:
        logger.exception("Multicard refund rejected for local order %s", order.id)
        order.payment_status = "refund_failed"
        order.refund_sync_status = "failed"
        order.refund_sync_error = "Provider rejected the refund request"
        order.payment_error = "The online refund needs staff assistance"
    except Exception:
        logger.exception("Multicard refund outcome unknown for local order %s", order.id)
        order.refund_sync_status = "unknown"
        order.refund_sync_error = "Provider refund outcome is unknown"
        order.payment_error = "The refund is being verified"
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


def _alipos_cancel_status_clause(statuses: tuple[str | None, ...]):
    return or_(
        *(
            Order.alipos_cancel_status.is_(None)
            if status is None
            else Order.alipos_cancel_status == status
            for status in statuses
        )
    )


async def _reload_order(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    return await db.get(Order, order_id, populate_existing=True)


async def _mark_alipos_cancel_unknown(
    db: AsyncSession,
    order_id: uuid.UUID,
    *,
    expected_statuses: tuple[str | None, ...],
) -> tuple[Order | None, bool]:
    result = await db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            _alipos_cancel_status_clause(expected_statuses),
        )
        .values(
            alipos_cancel_status="unknown",
            alipos_cancel_error=ALIPOS_CANCEL_UNKNOWN_ERROR,
        )
        .execution_options(synchronize_session=False)
    )
    changed = result.rowcount > 0
    await db.commit()
    return await _reload_order(db, order_id), changed


async def _finalize_alipos_cancelled(
    db: AsyncSession,
    order_id: uuid.UUID,
    *,
    expected_statuses: tuple[str | None, ...],
) -> tuple[Order | None, bool, bool]:
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    is_cancellable = Order.status.in_(ALIPOS_CANCELLABLE_LOCAL_STATUSES)
    is_terminal = Order.status.in_(TERMINAL_LOCAL_STATUSES)
    is_locally_cancelled = Order.status.in_(("CANCELLED", "CANCELED"))
    should_queue_refund = and_(
        Order.payment_status == "paid",
        Order.refund_sync_status.is_(None),
        or_(is_cancellable, is_locally_cancelled),
        Order.delivered_at.is_(None),
    )
    result = await db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            _alipos_cancel_status_clause(expected_statuses),
        )
        .values(
            status=case(
                (is_cancellable, "CANCELLED"),
                else_=Order.status,
            ),
            status_updated_at=case(
                (is_cancellable, now),
                else_=Order.status_updated_at,
            ),
            alipos_cancel_status=case(
                (or_(is_cancellable, is_terminal), "cancelled"),
                else_="not_cancelled",
            ),
            alipos_cancel_error=None,
            payment_status=case(
                (should_queue_refund, "refund_pending"),
                else_=Order.payment_status,
            ),
            refund_sync_status=case(
                (should_queue_refund, "queued"),
                else_=Order.refund_sync_status,
            ),
            refund_sync_error=case(
                (should_queue_refund, None),
                else_=Order.refund_sync_error,
            ),
        )
        .returning(Order.payment_status, Order.refund_sync_status)
        .execution_options(synchronize_session=False)
    )
    updated = result.one_or_none()
    should_dispatch_refund = bool(
        updated and updated[0] == "refund_pending" and updated[1] == "queued"
    )
    await db.commit()
    return (
        await _reload_order(db, order_id),
        updated is not None,
        should_dispatch_refund,
    )


async def _finalize_alipos_not_cancelled(
    db: AsyncSession,
    order_id: uuid.UUID,
    provider_status: str,
    *,
    expected_statuses: tuple[str | None, ...],
) -> tuple[Order | None, bool]:
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    is_cancellable = Order.status.in_(ALIPOS_CANCELLABLE_LOCAL_STATUSES)
    result = await db.execute(
        update(Order)
        .where(
            Order.id == order_id,
            _alipos_cancel_status_clause(expected_statuses),
        )
        .values(
            status=case(
                (is_cancellable, provider_status),
                else_=Order.status,
            ),
            status_updated_at=case(
                (is_cancellable, now),
                else_=Order.status_updated_at,
            ),
            alipos_cancel_status="not_cancelled",
            alipos_cancel_error=None,
        )
        .execution_options(synchronize_session=False)
    )
    changed = result.rowcount > 0
    await db.commit()
    return await _reload_order(db, order_id), changed


async def _reconcile_alipos_cancellation(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.alipos_cancel_status.in_(("sending", "unknown")),
            Order.alipos_order_id.is_not(None),
        )
        .execution_options(populate_existing=True)
    )
    order = result.scalar_one_or_none()
    if order is None:
        await db.commit()
        return False
    provider_order_id = str(order.alipos_order_id)
    await db.commit()

    try:
        current = await alipos_api.get_order_status(provider_order_id)
    except Exception:
        await _mark_alipos_cancel_unknown(
            db,
            order_id,
            expected_statuses=("sending", "unknown"),
        )
        return False

    provider_status = normalize_order_status(str(current.get("status") or ""))
    if not provider_status or provider_status == "NEW":
        await _mark_alipos_cancel_unknown(
            db,
            order_id,
            expected_statuses=("sending", "unknown"),
        )
        return False
    if provider_status == "CANCELLED":
        _, finalized, should_dispatch_refund = await _finalize_alipos_cancelled(
            db,
            order_id,
            expected_statuses=("sending", "unknown"),
        )
        if should_dispatch_refund:
            await _dispatch_queued_refund(db, order_id)
        return finalized

    _, finalized = await _finalize_alipos_not_cancelled(
        db,
        order_id,
        provider_status,
        expected_statuses=("sending", "unknown"),
    )
    return finalized


async def reconcile_unknown_alipos_cancellations(
    db: AsyncSession,
    *,
    limit: int = ALIPOS_CANCEL_RECONCILE_LIMIT,
) -> int:
    """GET-reconcile a bounded batch without repeating any cancellation DELETE."""
    bounded_limit = min(max(limit, 0), ALIPOS_CANCEL_RECONCILE_LIMIT)
    if bounded_limit == 0:
        return 0
    result = await db.execute(
        select(Order.id)
        .where(
            Order.alipos_cancel_status.in_(("sending", "unknown")),
            Order.alipos_order_id.is_not(None),
        )
        .order_by(Order.cancel_requested_at, Order.id)
        .limit(bounded_limit)
    )
    order_ids = list(result.scalars())
    await db.commit()

    reconciled = 0
    for order_id in order_ids:
        reconciled += int(await _reconcile_alipos_cancellation(db, order_id))
    return reconciled


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
        .execution_options(populate_existing=True)
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
        result = await db.execute(
            select(Order)
            .where(
                Order.id == order_id,
                Order.user_id == current_user.telegram_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise CustomerOrderNotFound("Order not found")
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

    if order.alipos_cancel_status == "cancelled":
        return order
    if order.alipos_cancel_status == "not_cancelled":
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )
    if order.alipos_cancel_status in {"sending", "unknown"}:
        await db.commit()
        await _reconcile_alipos_cancellation(db, order_id)
        order = await _reload_order(db, order_id)
        if order is None:
            raise CustomerOrderNotFound("Order not found")
        if order.alipos_cancel_status == "cancelled":
            return order
        if order.alipos_cancel_status == "not_cancelled":
            raise CancellationConflict(
                "The restaurant has already accepted this order, so it cannot be cancelled"
            )
        raise CancellationError("The cancellation result could not be confirmed")

    local_status = normalize_order_status(order.status)
    if local_status == "CANCELLED":
        return order
    if local_status in TERMINAL_LOCAL_STATUSES:
        raise CancellationConflict("This order can no longer be cancelled")
    if order.alipos_order_id is None or order.alipos_sync_status != "synced":
        raise CancellationConflict(
            "This order cannot be safely cancelled automatically; please ask staff"
        )

    provider_order_id = str(order.alipos_order_id)
    await db.commit()
    try:
        current = await alipos_api.get_order_status(provider_order_id)
    except Exception as exc:
        raise CancellationError("Could not verify the restaurant order status") from exc
    current_status = normalize_order_status(str(current.get("status") or ""))
    if not current_status:
        raise CancellationError("Could not verify the restaurant order status")
    if current_status == "CANCELLED":
        order, finalized, should_dispatch_refund = await _finalize_alipos_cancelled(
            db,
            order_id,
            expected_statuses=ALIPOS_CANCEL_PENDING_STATUSES,
        )
        if order is None:
            raise CustomerOrderNotFound("Order not found")
        if order.alipos_cancel_status == "not_cancelled":
            raise CancellationConflict(
                "The restaurant has already accepted this order, so it cannot be cancelled"
            )
        if not finalized and order.alipos_cancel_status != "cancelled":
            raise CancellationError("The cancellation result could not be confirmed")
        if should_dispatch_refund:
            dispatched = await _dispatch_queued_refund(db, order_id)
            return dispatched or order
        return order
    if current_status != "NEW":
        order, finalized = await _finalize_alipos_not_cancelled(
            db,
            order_id,
            current_status,
            expected_statuses=ALIPOS_CANCEL_PENDING_STATUSES,
        )
        if order is None:
            raise CustomerOrderNotFound("Order not found")
        if not finalized and order.alipos_cancel_status == "cancelled":
            return order
        if not finalized and order.alipos_cancel_status != "not_cancelled":
            raise CancellationError("The cancellation result could not be confirmed")
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )

    result = await db.execute(
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise CustomerOrderNotFound("Order not found")
    if order.alipos_cancel_status == "cancelled":
        await db.commit()
        return order
    if order.alipos_cancel_status == "not_cancelled":
        await db.commit()
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )
    if order.alipos_cancel_status in {"sending", "unknown"}:
        await db.commit()
        await _reconcile_alipos_cancellation(db, order_id)
        order = await _reload_order(db, order_id)
        if order is not None and order.alipos_cancel_status == "cancelled":
            return order
        if order is not None and order.alipos_cancel_status == "not_cancelled":
            raise CancellationConflict(
                "The restaurant has already accepted this order, so it cannot be cancelled"
            )
        raise CancellationError("The cancellation result could not be confirmed")
    if (
        order.alipos_cancel_status not in {None, "not_started"}
        or str(order.alipos_order_id) != provider_order_id
        or order.alipos_sync_status != "synced"
    ):
        await db.commit()
        raise CancellationConflict(
            "This order cannot be safely cancelled automatically; please ask staff"
        )
    revalidated_status = normalize_order_status(order.status)
    if revalidated_status == "CANCELLED":
        order, _, should_dispatch_refund = await _finalize_alipos_cancelled(
            db,
            order_id,
            expected_statuses=(order.alipos_cancel_status,),
        )
        if order is None:
            raise CustomerOrderNotFound("Order not found")
        if should_dispatch_refund:
            dispatched = await _dispatch_queued_refund(db, order_id)
            return dispatched or order
        return order
    if revalidated_status != "NEW":
        order.alipos_cancel_status = "not_cancelled"
        order.alipos_cancel_error = None
        await db.commit()
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )

    order.alipos_cancel_status = "sending"
    order.alipos_cancel_error = None
    order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    await db.commit()
    try:
        await alipos_api.cancel_order(
            provider_order_id,
            ALIPOS_CANCEL_COMMENT,
        )
    except Exception as exc:
        order, _ = await _mark_alipos_cancel_unknown(
            db,
            order_id,
            expected_statuses=("sending",),
        )
        if order is not None and order.alipos_cancel_status == "cancelled":
            return order
        raise CancellationError(
            "The cancellation result could not be confirmed"
        ) from exc

    order, finalized, should_dispatch_refund = await _finalize_alipos_cancelled(
        db,
        order_id,
        expected_statuses=("sending", "unknown"),
    )
    if order is None:
        raise CustomerOrderNotFound("Order not found")
    if order.alipos_cancel_status == "not_cancelled":
        raise CancellationConflict(
            "The restaurant has already accepted this order, so it cannot be cancelled"
        )
    if not finalized and order.alipos_cancel_status != "cancelled":
        raise CancellationError("The cancellation result could not be confirmed")
    if should_dispatch_refund:
        dispatched = await _dispatch_queued_refund(db, order_id)
        return dispatched or order
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
    if not can_use_inplace_online_payment(current_user):
        raise PaymentRetryConflict(
            "Online payment is not available for table orders"
        )
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

    if (
        body.discriminator == "inplace"
        and body.payment_method == "rahmat"
        and not can_use_inplace_online_payment(current_user)
    ):
        raise CustomerOrderError("Online payment is not available for table orders")

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
