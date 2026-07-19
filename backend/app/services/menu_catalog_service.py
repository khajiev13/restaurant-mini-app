import copy
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import Stoplist
from app.services import alipos_api

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricedCart:
    items: list[dict[str, Any]]
    items_cost: Decimal


class CartConflict(Exception):
    def __init__(self, changes: list[dict[str, Any]]):
        super().__init__("The cart no longer matches the current menu")
        self.changes = changes


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _modifier_catalog(menu_item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, dict):
            return

        modifier_id = value.get("id")
        if modifier_id and "price" in value:
            catalog[str(modifier_id)] = value
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    visit(menu_item.get("modifierGroups", []))
    return catalog


async def _stoplist_counts(
    db: AsyncSession,
    product_ids: set[uuid.UUID] | None = None,
) -> dict[str, int]:
    restaurant_id = uuid.UUID(settings.alipos_restaurant_id)
    query = select(Stoplist).where(Stoplist.restaurant_id == restaurant_id)
    if product_ids is not None:
        if not product_ids:
            return {}
        query = query.where(Stoplist.product_id.in_(product_ids))
    result = await db.execute(query)
    return {str(entry.product_id): entry.count for entry in result.scalars()}


def _availability_counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(values, list):
        return counts
    for value in values:
        if not isinstance(value, dict):
            continue
        identifier = next(
            (
                value.get(key)
                for key in ("id", "itemId", "productId", "modifierId")
                if value.get(key) is not None
            ),
            None,
        )
        if identifier is None:
            continue
        raw_count = next(
            (
                value.get(key)
                for key in ("count", "availableCount", "balance")
                if value.get(key) is not None
            ),
            None,
        )
        if raw_count is None and isinstance(value.get("isAvailable"), bool):
            raw_count = -1 if value["isAvailable"] else 0
        try:
            counts[str(identifier)] = int(raw_count)
        except (TypeError, ValueError):
            continue
    return counts


async def _live_availability_counts() -> tuple[dict[str, int], dict[str, int]]:
    try:
        payload = await alipos_api.get_menu_availability()
    except Exception:
        logger.warning("AliPOS live menu availability is unavailable; using webhooks")
        return {}, {}
    return (
        _availability_counts(payload.get("items")),
        _availability_counts(payload.get("modifiers")),
    )


def _most_restrictive_count(*values: int | None) -> int | None:
    finite = [value for value in values if value is not None and value >= 0]
    return min(finite) if finite else None


async def get_customer_menu(db: AsyncSession) -> dict[str, Any]:
    menu = copy.deepcopy(await alipos_api.get_menu())
    webhook_counts = await _stoplist_counts(db)
    live_item_counts, _ = await _live_availability_counts()
    for item in menu.get("items", []):
        item_id = str(item.get("id"))
        count = _most_restrictive_count(
            webhook_counts.get(item_id),
            live_item_counts.get(item_id),
        )
        item["available"] = count is None or count > 0
        item["availableCount"] = count
    return menu


async def price_cart(db: AsyncSession, requested_items: Iterable[Any]) -> PricedCart:
    requested = list(requested_items)
    menu = await alipos_api.get_menu(use_cache=False)
    catalog = {str(item.get("id")): item for item in menu.get("items", [])}
    valid_ids: set[uuid.UUID] = set()
    for item in requested:
        try:
            valid_ids.add(uuid.UUID(str(_value(item, "id"))))
        except (TypeError, ValueError):
            continue
    webhook_counts = await _stoplist_counts(db, valid_ids)
    live_item_counts, live_modifier_counts = await _live_availability_counts()

    changes: list[dict[str, Any]] = []
    priced_items: list[dict[str, Any]] = []
    total = Decimal("0")

    if not requested:
        raise CartConflict([{"reason": "empty_cart"}])

    for requested_item in requested:
        item_id = str(_value(requested_item, "id", ""))
        menu_item = catalog.get(item_id)
        if not menu_item:
            changes.append({"id": item_id, "reason": "missing"})
            continue

        quantity = _as_decimal(_value(requested_item, "quantity"))
        if quantity is None or quantity < Decimal("0.01") or quantity > Decimal("100"):
            changes.append({"id": item_id, "reason": "invalid_quantity"})
            continue

        available_count = _most_restrictive_count(
            webhook_counts.get(item_id),
            live_item_counts.get(item_id),
        )
        if available_count == 0:
            changes.append(
                {"id": item_id, "reason": "unavailable", "availableCount": 0}
            )
            continue
        if available_count is not None and available_count > 0 and quantity > available_count:
            changes.append(
                {
                    "id": item_id,
                    "reason": "quantity_unavailable",
                    "availableCount": available_count,
                }
            )
            continue

        item_price = _as_decimal(menu_item.get("price"))
        if item_price is None or item_price < 0:
            changes.append({"id": item_id, "reason": "invalid_menu_price"})
            continue
        submitted_item_price = _as_decimal(_value(requested_item, "price"))
        if submitted_item_price != item_price:
            changes.append({"id": item_id, "reason": "price_changed"})
            continue

        modifier_catalog = _modifier_catalog(menu_item)
        priced_modifiers: list[dict[str, Any]] = []
        modifier_total = Decimal("0")
        invalid_modifier = False
        for requested_modifier in _value(requested_item, "modifications", []) or []:
            modifier_id = str(_value(requested_modifier, "id", ""))
            modifier = modifier_catalog.get(modifier_id)
            modifier_quantity = _as_decimal(_value(requested_modifier, "quantity"))
            if (
                not modifier
                or modifier_quantity is None
                or modifier_quantity < Decimal("0.01")
                or modifier_quantity > Decimal("100")
            ):
                changes.append(
                    {"id": item_id, "modifierId": modifier_id, "reason": "invalid_modifier"}
                )
                invalid_modifier = True
                continue
            modifier_price = _as_decimal(modifier.get("price"))
            if modifier_price is None or modifier_price < 0:
                changes.append(
                    {"id": item_id, "modifierId": modifier_id, "reason": "invalid_modifier"}
                )
                invalid_modifier = True
                continue
            submitted_modifier_price = _as_decimal(_value(requested_modifier, "price"))
            if submitted_modifier_price != modifier_price:
                changes.append(
                    {"id": item_id, "modifierId": modifier_id, "reason": "price_changed"}
                )
                invalid_modifier = True
                continue
            modifier_available_count = _most_restrictive_count(
                live_modifier_counts.get(modifier_id)
            )
            if modifier_available_count == 0 or (
                modifier_available_count is not None
                and modifier_quantity > modifier_available_count
            ):
                changes.append(
                    {
                        "id": item_id,
                        "modifierId": modifier_id,
                        "reason": "modifier_unavailable",
                        "availableCount": modifier_available_count,
                    }
                )
                invalid_modifier = True
                continue
            modifier_total += modifier_price * modifier_quantity
            priced_modifiers.append(
                {
                    "id": modifier_id,
                    "name": modifier.get("name"),
                    "quantity": float(modifier_quantity),
                    "price": float(modifier_price),
                }
            )
        if invalid_modifier:
            continue

        total += item_price * quantity + modifier_total
        priced_items.append(
            {
                "id": item_id,
                "name": menu_item.get("name"),
                "quantity": float(quantity),
                "price": float(item_price),
                "modifications": priced_modifiers,
            }
        )

    if changes:
        raise CartConflict(changes)
    return PricedCart(items=priced_items, items_cost=total)
