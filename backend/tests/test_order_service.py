import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.config import settings
from app.models.models import User
from app.schemas.order import OrderCreate
from app.services import alipos_api
from app.services.menu_catalog_service import PricedCart
from app.services.order_service import create_customer_order
from app.services.table_access_service import TableDirectoryEntry

TABLE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
HALL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
CASH_PAYMENT_ID = "33333333-3333-4333-8333-333333333333"
ONLINE_PAYMENT_ID = "44444444-4444-4444-8444-444444444444"
PRICED_CART = PricedCart(
    items=[
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "name": "Classic Somsa",
            "quantity": 2.0,
            "price": 18000.0,
            "modifications": [],
        }
    ],
    items_cost=Decimal("36000"),
)
TABLE = TableDirectoryEntry(
    table_id=TABLE_ID,
    table_title="Stol 12",
    hall_id=HALL_ID,
    hall_title="Asosiy zal",
    service_percent=Decimal("10"),
)


def _body(payment_method: str = "cash") -> OrderCreate:
    return OrderCreate(
        items=[
            {
                "id": PRICED_CART.items[0]["id"],
                "name": "Untrusted name",
                "quantity": 2,
                "price": 1,
                "modifications": [],
            }
        ],
        phone_number="+998901112233",
        payment_method=payment_method,
        discriminator="inplace",
        table_access_token="signed-table-token",
        comment="Iltimos, piyozsiz",
    )


async def _customer(db_session) -> User:
    user = User(
        telegram_id=7301,
        first_name="Customer",
        last_name=None,
        username=None,
        phone_number="+998901112233",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_cash_inplace_order_submits_verified_table_and_service_total(db_session):
    user = await _customer(db_session)
    create_mock = AsyncMock(return_value={"orderId": str(uuid.uuid4())})

    with (
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=AsyncMock(return_value=TABLE),
        ),
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=create_mock,
        ),
    ):
        order = await create_customer_order(db_session, user, _body())

    payload = create_mock.await_args.args[0]
    assert payload["discriminator"] == "inplace"
    assert payload["tableId"] == str(TABLE_ID)
    assert payload["paymentInfo"] == {
        "paymentId": CASH_PAYMENT_ID,
        "itemsCost": 36000.0,
        "total": 39600.0,
        "deliveryFee": 0.0,
    }
    assert payload["items"] == [
        {
            "id": PRICED_CART.items[0]["id"],
            "quantity": 2.0,
            "price": 18000.0,
            "modifications": [],
        }
    ]
    assert order.items == PRICED_CART.items
    assert float(order.total_amount) == 39600
    assert order.alipos_sync_status == "synced"


@pytest.mark.asyncio
async def test_online_inplace_order_waits_for_verified_payment(db_session):
    user = await _customer(db_session)
    create_mock = AsyncMock()
    invoice_mock = AsyncMock(
        return_value={
            "uuid": "invoice-uuid",
            "checkout_url": "https://pay.example/checkout",
        }
    )

    with (
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=AsyncMock(return_value=TABLE),
        ),
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=create_mock,
        ),
        patch(
            "app.services.order_service.multicard_api.create_invoice",
            new=invoice_mock,
        ),
    ):
        order = await create_customer_order(db_session, user, _body("rahmat"))

    create_mock.assert_not_awaited()
    invoice_mock.assert_awaited_once()
    assert invoice_mock.await_args.kwargs["amount_tiyin"] == 3_960_000
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_status == "pending"
    assert order.alipos_sync_status == "awaiting_payment"


@pytest.mark.asyncio
async def test_alipos_create_order_makes_one_attempt_on_unknown_outcome():
    request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
    client = Mock()
    client.request = request
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.alipos_api._get_token", new=AsyncMock(return_value="token")
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(alipos_api.AliPOSUnknownOutcome):
            await alipos_api.create_order({"eatsId": "stable-id"})

    request.assert_awaited_once()


@pytest.mark.asyncio
async def test_online_payment_method_uses_configured_id_only_when_live(monkeypatch):
    monkeypatch.setattr(settings, "alipos_online_order_payment_id", ONLINE_PAYMENT_ID)
    from app.services.order_service import resolve_payment_method_id

    with patch(
        "app.services.order_service.alipos_api.get_payment_methods",
        new=AsyncMock(
            return_value=[
                {"id": ONLINE_PAYMENT_ID, "title": "online-order"},
                {"id": CASH_PAYMENT_ID, "title": "Наличные"},
            ]
        ),
    ):
        assert await resolve_payment_method_id("online") == ONLINE_PAYMENT_ID
