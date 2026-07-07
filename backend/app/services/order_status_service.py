import datetime

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
