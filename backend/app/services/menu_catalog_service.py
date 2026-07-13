import copy
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import Stoplist
from app.services import alipos_api


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


async def get_customer_menu(db: AsyncSession) -> dict[str, Any]:
    menu = copy.deepcopy(await alipos_api.get_menu())
    counts = await _stoplist_counts(db)
    for item in menu.get("items", []):
        count = counts.get(str(item.get("id")))
        item["available"] = count is None or count == -1 or count > 0
        item["availableCount"] = count if count is not None and count >= 0 else None
    return menu


async def price_cart(db: AsyncSession, requested_items: Iterable[Any]) -> PricedCart:
    requested = list(requested_items)
    menu = await alipos_api.get_menu()
    catalog = {str(item.get("id")): item for item in menu.get("items", [])}
    valid_ids: set[uuid.UUID] = set()
    for item in requested:
        try:
            valid_ids.add(uuid.UUID(str(_value(item, "id"))))
        except (TypeError, ValueError):
            continue
    counts = await _stoplist_counts(db, valid_ids)

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
        if quantity is None or quantity <= 0:
            changes.append({"id": item_id, "reason": "invalid_quantity"})
            continue

        available_count = counts.get(item_id)
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

        modifier_catalog = _modifier_catalog(menu_item)
        priced_modifiers: list[dict[str, Any]] = []
        modifier_total = Decimal("0")
        invalid_modifier = False
        for requested_modifier in _value(requested_item, "modifications", []) or []:
            modifier_id = str(_value(requested_modifier, "id", ""))
            modifier = modifier_catalog.get(modifier_id)
            modifier_quantity = _as_decimal(_value(requested_modifier, "quantity"))
            if not modifier or modifier_quantity is None or modifier_quantity <= 0:
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
