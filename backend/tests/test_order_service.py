import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.models import Order, User
from app.schemas.order import OrderCreate
from app.services import alipos_api
from app.services.menu_catalog_service import PricedCart
from app.services.order_service import (
    create_customer_order,
    expire_due_payment_orders,
    list_recoverable_alipos_order_ids,
    list_recoverable_refund_order_ids,
    reconcile_unknown_refunds,
)
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


@pytest.fixture(autouse=True)
def valid_table_token_claims(monkeypatch):
    monkeypatch.setattr(
        "app.services.order_service.table_access.verify_access_token",
        Mock(return_value=SimpleNamespace(
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        )),
    )


def _body(
    payment_method: str = "cash",
    client_request_id: uuid.UUID | None = None,
) -> OrderCreate:
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
        client_request_id=client_request_id,
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
async def test_repeated_customer_request_id_returns_one_cash_order(db_session):
    user = await _customer(db_session)
    request_id = uuid.uuid4()
    create_mock = AsyncMock(return_value={"orderId": str(uuid.uuid4())})
    resolve_table = AsyncMock(return_value=TABLE)
    price = AsyncMock(return_value=PRICED_CART)

    with (
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=resolve_table,
        ),
        patch("app.services.order_service.price_cart", new=price),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create_mock),
    ):
        first = await create_customer_order(
            db_session,
            user,
            _body(client_request_id=request_id),
        )
        second = await create_customer_order(
            db_session,
            user,
            _body(client_request_id=request_id),
        )

    assert first.id == second.id
    create_mock.assert_awaited_once()
    resolve_table.assert_awaited_once()
    price.assert_awaited_once()


@pytest.mark.asyncio
async def test_idempotency_race_dispatches_the_winning_queued_cash_order():
    user = User(
        telegram_id=7302,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    request_id = uuid.uuid4()
    winner = Mock(
        id=uuid.uuid4(),
        client_request_id=request_id,
        alipos_sync_status="queued",
    )
    no_existing = Mock()
    no_existing.scalar_one_or_none.return_value = None
    winner_result = Mock()
    winner_result.scalar_one_or_none.return_value = winner
    db = AsyncMock()
    db.add = Mock()
    db.execute.side_effect = [no_existing, winner_result]
    db.commit.side_effect = IntegrityError("insert", {}, RuntimeError("duplicate"))

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
            "app.services.order_service._submit_queued_alipos_order",
            new=AsyncMock(return_value=winner),
        ) as submit,
    ):
        returned = await create_customer_order(
            db,
            user,
            _body(client_request_id=request_id),
        )

    db.rollback.assert_awaited_once()
    submit.assert_awaited_once_with(db, winner.id)
    assert returned is winner


async def _queued_order(
    db_session,
    user: User,
    *,
    payment_method: str,
    payment_status: str | None,
) -> Order:
    order = Order(
        user_id=user.telegram_id,
        items=[],
        delivery_info={"clientName": "Customer", "phoneNumber": "+998901112233"},
        items_cost=10000,
        total_amount=11000,
        delivery_fee=0,
        payment_method=payment_method,
        payment_status=payment_status,
        discriminator="inplace",
        table_id=TABLE_ID,
        alipos_eats_id=f"recover-{uuid.uuid4().hex}",
        alipos_sync_status="queued",
        status="NEW",
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_recovery_includes_cash_and_paid_online_but_not_unpaid_online(db_session):
    user = await _customer(db_session)
    cash = await _queued_order(
        db_session,
        user,
        payment_method="cash",
        payment_status=None,
    )
    paid = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    unpaid = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="pending",
    )

    recoverable = await list_recoverable_alipos_order_ids(db_session)

    assert set(recoverable) == {cash.id, paid.id}
    assert unpaid.id not in recoverable


@pytest.mark.asyncio
async def test_refund_recovery_only_dispatches_never_attempted_refunds(db_session):
    user = await _customer(db_session)
    queued = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    queued.refund_sync_status = "queued"
    queued.multicard_payment_uuid = "queued-payment"
    unknown = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    unknown.refund_sync_status = "unknown"
    unknown.multicard_payment_uuid = "unknown-payment"
    await db_session.commit()

    recoverable = await list_recoverable_refund_order_ids(db_session)

    assert recoverable == [queued.id]


@pytest.mark.asyncio
async def test_unknown_refund_is_reconciled_without_repeating_delete(db_session):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    order.refund_sync_status = "unknown"
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()

    with patch(
        "app.services.order_service.multicard_api.get_payment",
        new=AsyncMock(return_value={"status": "revert"}),
    ) as lookup:
        reconciled = await reconcile_unknown_refunds(db_session)

    await db_session.refresh(order)
    assert reconciled == 1
    lookup.assert_awaited_once_with("payment-uuid")
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"


async def _expired_online_order(db_session, user: User) -> Order:
    order = Order(
        user_id=user.telegram_id,
        items=[],
        delivery_info={"clientName": "Customer", "phoneNumber": "+998901112233"},
        items_cost=10000,
        total_amount=11000,
        delivery_fee=0,
        payment_method="rahmat",
        payment_provider="multicard",
        payment_status="pending",
        payment_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        - datetime.timedelta(seconds=1),
        multicard_invoice_uuid="invoice-uuid",
        discriminator="inplace",
        table_id=TABLE_ID,
        alipos_eats_id=f"expire-{uuid.uuid4().hex}",
        alipos_sync_status="awaiting_payment",
        status="AWAITING_PAYMENT",
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_expiry_leaves_order_payable_when_invoice_cancel_is_unconfirmed(db_session):
    user = await _customer(db_session)
    order = await _expired_online_order(db_session, user)

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=AsyncMock(side_effect=RuntimeError("already paid or unavailable")),
    ):
        expired = await expire_due_payment_orders(
            db_session,
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )

    await db_session.refresh(order)
    assert expired == 0
    assert order.payment_status == "pending"
    assert order.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_expiry_cancels_order_only_after_invoice_cancel_is_confirmed(db_session):
    user = await _customer(db_session)
    order = await _expired_online_order(db_session, user)
    cancel_invoice = AsyncMock()

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=cancel_invoice,
    ):
        expired = await expire_due_payment_orders(
            db_session,
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )

    await db_session.refresh(order)
    assert expired == 1
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    assert order.payment_status == "expired"
    assert order.status == "CANCELLED"


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
