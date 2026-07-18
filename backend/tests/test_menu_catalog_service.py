import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.models import Stoplist
from app.services import alipos_api
from app.services.menu_catalog_service import (
    CartConflict,
    get_customer_menu,
    price_cart,
)

ITEM_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_ITEM_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
MENU = {
    "categories": [{"id": "category-1", "name": "Somsa", "sortOrder": 0}],
    "items": [
        {
            "id": str(ITEM_ID),
            "categoryId": "category-1",
            "name": "Classic Somsa",
            "price": 18000,
            "sortOrder": 0,
            "modifierGroups": [],
        }
    ],
}


@pytest.fixture(autouse=True)
def mock_live_availability(monkeypatch):
    monkeypatch.setattr(
        alipos_api,
        "get_menu_availability",
        AsyncMock(return_value={"items": [], "modifiers": []}),
    )


@pytest.mark.asyncio
async def test_customer_menu_merges_stoplist_without_mutating_cached_menu(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=MENU))
    db_session.add(
        Stoplist(
            product_id=ITEM_ID,
            restaurant_id=uuid.UUID(settings.alipos_restaurant_id),
            count=0,
        )
    )
    await db_session.flush()

    result = await get_customer_menu(db_session)

    assert result["items"][0]["available"] is False
    assert result["items"][0]["availableCount"] == 0
    assert "available" not in MENU["items"][0]


@pytest.mark.asyncio
async def test_price_cart_uses_current_server_name_and_price(db_session, monkeypatch):
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=MENU))

    priced = await price_cart(
        db_session,
        [
            {
                "id": str(ITEM_ID),
                "name": "Stale name",
                "quantity": 2,
                "price": 1,
                "modifications": [],
            }
        ],
    )

    assert priced.items_cost == Decimal("36000")
    assert priced.items[0] == {
        "id": str(ITEM_ID),
        "name": "Classic Somsa",
        "quantity": 2.0,
        "price": 18000.0,
        "modifications": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested", "reason"),
    [
        ({"id": str(OTHER_ITEM_ID), "quantity": 1}, "missing"),
        ({"id": str(ITEM_ID), "quantity": 0}, "invalid_quantity"),
        ({"id": str(ITEM_ID), "quantity": 0.001}, "invalid_quantity"),
        ({"id": str(ITEM_ID), "quantity": 101}, "invalid_quantity"),
    ],
)
async def test_price_cart_returns_structured_conflicts(
    db_session,
    monkeypatch,
    requested,
    reason,
):
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=MENU))

    with pytest.raises(CartConflict) as exc_info:
        await price_cart(db_session, [requested])

    assert exc_info.value.changes[0]["reason"] == reason


@pytest.mark.asyncio
async def test_price_cart_rejects_quantity_above_stoplist_count(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=MENU))
    db_session.add(
        Stoplist(
            product_id=ITEM_ID,
            restaurant_id=uuid.UUID(settings.alipos_restaurant_id),
            count=1,
        )
    )
    await db_session.flush()

    with pytest.raises(CartConflict) as exc_info:
        await price_cart(db_session, [{"id": str(ITEM_ID), "quantity": 2}])

    assert exc_info.value.changes == [
        {
            "id": str(ITEM_ID),
            "reason": "quantity_unavailable",
            "availableCount": 1,
        }
    ]


@pytest.mark.asyncio
async def test_customer_menu_merges_live_availability(db_session, monkeypatch):
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=MENU))
    monkeypatch.setattr(
        alipos_api,
        "get_menu_availability",
        AsyncMock(return_value={
            "items": [{"id": str(ITEM_ID), "count": 0}],
            "modifiers": [],
        }),
    )

    result = await get_customer_menu(db_session)

    assert result["items"][0]["available"] is False
    assert result["items"][0]["availableCount"] == 0


@pytest.mark.asyncio
async def test_price_cart_rejects_unavailable_live_modifier(db_session, monkeypatch):
    modifier_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    menu = {
        **MENU,
        "items": [{
            **MENU["items"][0],
            "modifierGroups": [{
                "id": "group-1",
                "modifiers": [{"id": str(modifier_id), "name": "Cheese", "price": 2000}],
            }],
        }],
    }
    monkeypatch.setattr(alipos_api, "get_menu", AsyncMock(return_value=menu))
    monkeypatch.setattr(
        alipos_api,
        "get_menu_availability",
        AsyncMock(return_value={
            "items": [],
            "modifiers": [{"id": str(modifier_id), "count": 0}],
        }),
    )

    with pytest.raises(CartConflict) as exc_info:
        await price_cart(db_session, [{
            "id": str(ITEM_ID),
            "quantity": 1,
            "modifications": [{"id": str(modifier_id), "quantity": 1}],
        }])

    assert exc_info.value.changes == [{
        "id": str(ITEM_ID),
        "modifierId": str(modifier_id),
        "reason": "modifier_unavailable",
        "availableCount": 0,
    }]
