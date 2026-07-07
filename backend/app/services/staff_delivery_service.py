import datetime
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Order, User
from app.services import alipos_api
from app.services.order_status_service import apply_alipos_status_update_for_order
from app.services.permissions import require_staff

AVAILABLE_STATUS = "TAKEN_BY_COURIER"
DELIVERED_STATUS = "DELIVERED"
DELIVERY_DISCRIMINATOR = "delivery"
CANCELLED_STATUSES = {"CANCELLED", "CANCELED"}
TERMINAL_STATUSES = {DELIVERED_STATUS, *CANCELLED_STATUSES}
ACTIVE_ORDER_CONFLICT = "Finish your active delivery before taking another order."


def _staff_order_options():
    return (
        selectinload(Order.user),
        selectinload(Order.address),
        selectinload(Order.assigned_staff),
    )


def _active_order_filters(staff_id: int):
    return (
        Order.assigned_staff_id == staff_id,
        Order.discriminator == DELIVERY_DISCRIMINATOR,
        Order.delivered_at.is_(None),
        Order.status.not_in(TERMINAL_STATUSES),
    )


def _can_handle_delivery_payment(order: Order) -> bool:
    return order.payment_method == "cash" or order.payment_status == "paid"


async def _load_staff_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Order | None:
    query = (
        select(Order)
        .options(*_staff_order_options())
        .where(Order.id == order_id, Order.discriminator == DELIVERY_DISCRIMINATOR)
    )
    if for_update:
        query = query.with_for_update()

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _require_staff_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Order:
    order = await _load_staff_order(db, order_id, for_update=for_update)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return order


async def _ensure_no_active_order(db: AsyncSession, staff_id: int) -> None:
    result = await db.execute(
        select(Order.id).where(*_active_order_filters(staff_id)).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ACTIVE_ORDER_CONFLICT,
        )


async def list_available_orders(db: AsyncSession, current_user: User) -> list[Order]:
    require_staff(current_user)

    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(
            Order.discriminator == DELIVERY_DISCRIMINATOR,
            Order.status == AVAILABLE_STATUS,
            Order.assigned_staff_id.is_(None),
            or_(Order.payment_method == "cash", Order.payment_status == "paid"),
        )
        .order_by(Order.created_at.asc())
    )
    return list(result.scalars().all())


async def get_active_order(db: AsyncSession, current_user: User) -> Order | None:
    require_staff(current_user)

    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(*_active_order_filters(current_user.telegram_id))
        .order_by(Order.assigned_at.asc(), Order.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_completed_orders(db: AsyncSession, current_user: User) -> list[Order]:
    require_staff(current_user)

    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(
            Order.assigned_staff_id == current_user.telegram_id,
            Order.discriminator == DELIVERY_DISCRIMINATOR,
            Order.status == DELIVERED_STATUS,
            Order.delivered_at.is_not(None),
        )
        .order_by(Order.delivered_at.desc(), Order.created_at.desc())
    )
    return list(result.scalars().all())


async def get_staff_order(
    db: AsyncSession,
    current_user: User,
    order_id: uuid.UUID,
) -> Order:
    require_staff(current_user)

    order = await _require_staff_order(db, order_id)
    if order.assigned_staff_id is None:
        if order.status != AVAILABLE_STATUS or not _can_handle_delivery_payment(order):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return order

    if order.assigned_staff_id != current_user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Order is assigned to another staff member.",
        )
    return order


async def take_order(
    db: AsyncSession,
    current_user: User,
    order_id: uuid.UUID,
) -> Order:
    require_staff(current_user)
    await _ensure_no_active_order(db, current_user.telegram_id)

    order = await _require_staff_order(db, order_id, for_update=True)

    if order.assigned_staff_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order was already taken by another staff member.",
        )

    if order.alipos_order_id:
        try:
            alipos_data = await alipos_api.get_order_status(str(order.alipos_order_id))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not refresh order status. Try again.",
            ) from exc

        if await apply_alipos_status_update_for_order(
            db,
            order,
            alipos_data.get("status", order.status),
            alipos_data.get("orderNumber"),
        ):
            await db.flush()

    if order.status != AVAILABLE_STATUS:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order is no longer available.",
        )

    if not _can_handle_delivery_payment(order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order is not ready for delivery payment handling.",
        )

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.assigned_staff_id = current_user.telegram_id
    order.assigned_at = now

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ACTIVE_ORDER_CONFLICT,
        ) from exc

    return await _require_staff_order(db, order.id)


async def mark_order_delivered(
    db: AsyncSession,
    current_user: User,
    order_id: uuid.UUID,
) -> Order:
    require_staff(current_user)

    order = await _require_staff_order(db, order_id, for_update=True)

    if order.assigned_staff_id != current_user.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned staff member can complete this order.",
        )

    if order.status in CANCELLED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order was cancelled.",
        )

    if order.status == DELIVERED_STATUS:
        if order.delivered_at is None:
            now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            order.delivered_at = now
            order.status_updated_at = now
            await db.commit()
            return await _require_staff_order(db, order.id)
        return order

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.status = DELIVERED_STATUS
    order.delivered_at = now
    order.status_updated_at = now
    await db.commit()

    return await _require_staff_order(db, order.id)
