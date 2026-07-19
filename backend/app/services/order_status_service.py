import datetime

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Order

TERMINAL_LOCAL_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}
KNOWN_STATUS_RANKS = {
    "NEW": 0,
    "ACCEPTED_BY_RESTAURANT": 1,
    "READY": 2,
    "TAKEN_BY_COURIER": 3,
    "DELIVERED": 4,
}


def normalize_order_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "CANCELED":
        return "CANCELLED"
    return normalized


def parse_alipos_updated_at(value: object) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(datetime.UTC).replace(tzinfo=None)


def _is_backward_known_transition(current: str, next_status: str) -> bool:
    current_rank = KNOWN_STATUS_RANKS.get(normalize_order_status(current))
    next_rank = KNOWN_STATUS_RANKS.get(next_status)
    return (
        current_rank is not None
        and next_rank is not None
        and next_rank < current_rank
    )


def apply_alipos_status_update(
    order: Order,
    status_value: str,
    order_number: str | None = None,
    provider_updated_at: datetime.datetime | None = None,
) -> bool:
    if normalize_order_status(order.status) in TERMINAL_LOCAL_STATUSES:
        return False

    next_status = normalize_order_status(status_value)
    if _is_backward_known_transition(order.status, next_status):
        return False
    if (
        provider_updated_at is not None
        and order.alipos_status_updated_at is not None
        and provider_updated_at < order.alipos_status_updated_at
    ):
        return False

    status_or_number_changed = False
    changed = False
    if order.status != next_status:
        order.status = next_status
        status_or_number_changed = True
        changed = True
    if order_number and order.order_number != order_number:
        order.order_number = order_number
        status_or_number_changed = True
        changed = True
    if (
        provider_updated_at is not None
        and order.alipos_status_updated_at != provider_updated_at
    ):
        order.alipos_status_updated_at = provider_updated_at
        changed = True
    if status_or_number_changed:
        order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
    return changed


async def apply_alipos_status_update_for_order(
    db: AsyncSession,
    order: Order,
    status_value: str,
    order_number: str | None = None,
    *,
    provider_updated_at: datetime.datetime | None = None,
    expected_claim_token: datetime.datetime | None = None,
    status_checked_at: datetime.datetime | None = None,
) -> bool:
    await db.refresh(order)
    if normalize_order_status(order.status) in TERMINAL_LOCAL_STATUSES:
        return False

    next_status = normalize_order_status(status_value)
    if _is_backward_known_transition(order.status, next_status):
        return False
    if (
        provider_updated_at is not None
        and order.alipos_status_updated_at is not None
        and provider_updated_at < order.alipos_status_updated_at
    ):
        return False

    status_changed = order.status != next_status
    number_changed = bool(order_number and order.order_number != order_number)
    provider_time_changed = bool(
        provider_updated_at is not None
        and order.alipos_status_updated_at != provider_updated_at
    )
    checked_time_changed = bool(
        status_checked_at is not None
        and order.alipos_status_checked_at != status_checked_at
    )
    if not any(
        (status_changed, number_changed, provider_time_changed, checked_time_changed)
    ):
        return False

    values: dict[str, object] = {"status": next_status}
    if status_changed or number_changed:
        values["status_updated_at"] = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
    if order_number:
        values["order_number"] = order_number
    if provider_updated_at is not None:
        values["alipos_status_updated_at"] = provider_updated_at
    if status_checked_at is not None:
        values["alipos_status_checked_at"] = status_checked_at

    conditions = [
        Order.id == order.id,
        Order.status.not_in(TERMINAL_LOCAL_STATUSES),
        Order.status == order.status,
        Order.order_number.is_not_distinct_from(order.order_number),
        Order.alipos_status_updated_at.is_not_distinct_from(
            order.alipos_status_updated_at
        ),
    ]
    if provider_updated_at is not None:
        conditions.append(
            or_(
                Order.alipos_status_updated_at.is_(None),
                Order.alipos_status_updated_at <= provider_updated_at,
            )
        )
    if expected_claim_token is not None:
        conditions.append(
            Order.alipos_status_check_attempted_at == expected_claim_token
        )

    result = await db.execute(
        update(Order)
        .where(*conditions)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await db.refresh(order)
    return result.rowcount > 0
