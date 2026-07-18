import datetime

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Order

TERMINAL_LOCAL_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}


def normalize_order_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "CANCELED":
        return "CANCELLED"
    return normalized


def apply_alipos_status_update(
    order: Order,
    status_value: str,
    order_number: str | None = None,
) -> bool:
    if normalize_order_status(order.status) in TERMINAL_LOCAL_STATUSES:
        return False

    next_status = normalize_order_status(status_value)
    changed = False

    if order.status != next_status:
        order.status = next_status
        changed = True

    if order_number and order.order_number != order_number:
        order.order_number = order_number
        changed = True

    if changed:
        order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    return changed


async def apply_alipos_status_update_for_order(
    db: AsyncSession,
    order: Order,
    status_value: str,
    order_number: str | None = None,
) -> bool:
    if normalize_order_status(order.status) in TERMINAL_LOCAL_STATUSES:
        return False

    next_status = normalize_order_status(status_value)
    values = {
        "status": next_status,
        "status_updated_at": datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    }
    changed_conditions = [Order.status.is_distinct_from(next_status)]

    if order_number:
        values["order_number"] = order_number
        changed_conditions.append(Order.order_number.is_distinct_from(order_number))

    result = await db.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.status.not_in(TERMINAL_LOCAL_STATUSES),
            or_(*changed_conditions),
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await db.refresh(order)
    return result.rowcount > 0
