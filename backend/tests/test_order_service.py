import datetime
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.models import Order, User
from app.schemas.order import OrderCreate
from app.services import alipos_api, multicard_api
from app.services.menu_catalog_service import PricedCart
from app.services.order_service import (
    CustomerOrderError,
    OrderSubmissionRejected,
    _dispatch_queued_refund,
    _submit_queued_alipos_order,
    create_customer_order,
    dispatch_queued_alipos_order,
    expire_due_payment_orders,
    list_recoverable_alipos_order_ids,
    list_recoverable_refund_order_ids,
    reconcile_unknown_refunds,
    submit_order_to_alipos,
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


def _delivery_body(payment_method: str = "rahmat") -> OrderCreate:
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
        discriminator="delivery",
        delivery_address="Yakkasaray District, Shota Rustaveli 45",
        latitude="41.2995",
        longitude="69.2401",
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
        "total": 36000.0,
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


def test_alipos_integration_total_preserves_delivery_total():
    from app.services.order_service import _alipos_integration_total

    delivery = SimpleNamespace(
        discriminator="delivery",
        items_cost=Decimal("36000"),
        total_amount=Decimal("41000"),
    )

    assert _alipos_integration_total(delivery) == Decimal("41000")


@pytest.mark.asyncio
async def test_online_inplace_order_waits_for_verified_payment(db_session, monkeypatch):
    user = await _customer(db_session)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "7301")
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
async def test_disabled_online_inplace_order_is_rejected_before_side_effects(
    db_session,
    monkeypatch,
):
    user = await _customer(db_session)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "")
    resolve_table = AsyncMock(return_value=TABLE)
    price = AsyncMock(return_value=PRICED_CART)
    invoice = AsyncMock(
        return_value={
            "uuid": "unexpected-invoice-uuid",
            "checkout_url": "https://pay.example/unexpected-checkout",
        }
    )

    with (
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=resolve_table,
        ),
        patch("app.services.order_service.price_cart", new=price),
        patch("app.services.order_service.multicard_api.create_invoice", new=invoice),
    ):
        with pytest.raises(
            CustomerOrderError,
            match="Online payment is not available for table orders",
        ):
            await create_customer_order(db_session, user, _body("rahmat"))

    resolve_table.assert_not_awaited()
    price.assert_not_awaited()
    invoice.assert_not_awaited()
    result = await db_session.execute(
        select(Order).where(Order.user_id == user.telegram_id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_delivery_online_payment_remains_available(db_session, monkeypatch):
    user = await _customer(db_session)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "")
    invoice = AsyncMock(
        return_value={
            "uuid": "delivery-invoice-uuid",
            "checkout_url": "https://pay.example/delivery-checkout",
        }
    )

    with (
        patch(
            "app.services.order_service.price_cart",
            new=AsyncMock(return_value=PRICED_CART),
        ),
        patch("app.services.order_service.multicard_api.create_invoice", new=invoice),
    ):
        order = await create_customer_order(
            db_session,
            user,
            _delivery_body(),
        )

    invoice.assert_awaited_once()
    assert order.discriminator == "delivery"
    assert order.payment_status == "pending"


@pytest.mark.asyncio
async def test_existing_online_inplace_order_is_returned_after_capability_disabled(
    db_session,
    monkeypatch,
):
    user = await _customer(db_session)
    request_id = uuid.uuid4()
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", True)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "")
    resolve_table = AsyncMock(return_value=TABLE)
    price = AsyncMock(return_value=PRICED_CART)
    invoice = AsyncMock(
        return_value={
            "uuid": "invoice-uuid",
            "checkout_url": "https://pay.example/checkout",
        }
    )

    with (
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=resolve_table,
        ),
        patch("app.services.order_service.price_cart", new=price),
        patch("app.services.order_service.multicard_api.create_invoice", new=invoice),
    ):
        first = await create_customer_order(
            db_session,
            user,
            _body("rahmat", client_request_id=request_id),
        )
        monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
        second = await create_customer_order(
            db_session,
            user,
            _body("rahmat", client_request_id=request_id),
        )

    assert second.id == first.id
    invoice.assert_awaited_once()
    resolve_table.assert_awaited_once()
    price.assert_awaited_once()


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
async def test_interrupted_alipos_send_is_recovered_as_unknown(db_session):
    from app.services.order_service import recover_interrupted_alipos_orders

    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="cash",
        payment_status=None,
    )
    order.alipos_sync_status = "sending"
    order.alipos_order_id = None
    await db_session.commit()

    recovered = await recover_interrupted_alipos_orders(db_session)

    await db_session.refresh(order)
    assert recovered == 1
    assert order.alipos_sync_status == "unknown"
    assert order.status == "SYNC_UNKNOWN"


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


@pytest.mark.asyncio
async def test_malformed_refund_success_is_unknown_without_repeating_delete(
    db_session,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    order.refund_sync_status = "queued"
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()

    response = httpx.Response(
        200,
        content=b"not-json",
        request=httpx.Request("DELETE", "https://multicard.example/payment/payment-uuid"),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        await _dispatch_queued_refund(db_session, order.id)
        await _dispatch_queued_refund(db_session, order.id)

    await db_session.refresh(order)
    client.delete.assert_awaited_once()
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "unknown"
    assert order.refund_sync_error == "Provider refund outcome is unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_code",
    [
        "ERROR_UNKNOWN",
        "ERROR_CALLBACK_TIMEOUT",
        "ERROR_DEBIT_UNKNOWN",
        "ERROR_TRANS_NOT_READY",
    ],
)
async def test_ambiguous_refund_4xx_is_unknown_without_repeating_delete(
    db_session,
    error_code,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    order.refund_sync_status = "queued"
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()

    response = httpx.Response(
        400,
        json={
            "success": False,
            "error": {"code": error_code, "details": "provider-secret"},
        },
        request=httpx.Request("DELETE", "https://multicard.example/payment/payment-uuid"),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        await _dispatch_queued_refund(db_session, order.id)
        await _dispatch_queued_refund(db_session, order.id)

    await db_session.refresh(order)
    client.delete.assert_awaited_once()
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "unknown"
    assert order.refund_sync_error == "Provider refund outcome is unknown"


@pytest.mark.asyncio
async def test_refund_http_rejection_uses_explicit_definite_outcome():
    response = httpx.Response(
        400,
        json={
            "success": False,
            "error": {"code": "ERROR_FIELDS", "details": "customer-secret"},
        },
        request=httpx.Request("DELETE", "https://multicard.example/payment/payment-uuid"),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.RefundRejected) as exc_info:
            await multicard_api.refund_payment("payment-uuid")

    client.delete.assert_awaited_once()
    assert getattr(exc_info.value, "status_code", None) == 400
    assert "customer-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_refund_success_without_revert_status_is_unknown():
    response = httpx.Response(
        200,
        json={"success": True, "data": {"status": "success"}},
        request=httpx.Request("DELETE", "https://multicard.example/payment/payment-uuid"),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.RefundOutcomeUnknown):
            await multicard_api.refund_payment("payment-uuid")

    client.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_server_error_is_unknown_after_single_delete():
    response = httpx.Response(
        500,
        json={"success": False, "error": {"code": "ERROR_UNKNOWN"}},
        request=httpx.Request("DELETE", "https://multicard.example/payment/payment-uuid"),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.RefundOutcomeUnknown):
            await multicard_api.refund_payment("payment-uuid")

    client.delete.assert_awaited_once()


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
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 405, 422])
async def test_alipos_create_order_rejected_response_is_status_only(status_code):
    response = httpx.Response(
        status_code,
        json={"detail": "customer-secret"},
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.alipos_api._get_token", new=AsyncMock(return_value="token")
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(alipos_api.AliPOSRejected) as exc:
            await alipos_api.create_order({"eatsId": "stable-id"})

    assert exc.value.status_code == status_code
    assert "customer-secret" not in str(exc.value)
    client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_definite_rejection_logging_excludes_provider_context(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="cash",
        payment_status=None,
    )
    provider_url = "https://provider-url-secret.example/order"
    provider_token = "provider-token-secret"
    provider_body = "provider-body-secret"
    response = httpx.Response(
        400,
        json={"detail": provider_body},
        request=httpx.Request(
            "POST",
            f"{provider_url}?access_token={provider_token}",
        ),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    @asynccontextmanager
    async def session_override():
        yield db_session

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": CASH_PAYMENT_ID, "title": "Наличные"}]
            ),
        ),
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value=provider_token),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        patch("app.services.order_service.async_session", session_override),
        caplog.at_level("WARNING", logger="app.services.order_service"),
    ):
        await dispatch_queued_alipos_order(order.id)

    dispatch_record = next(
        record
        for record in caplog.records
        if record.name == "app.services.order_service"
        and record.getMessage() == "alipos_dispatch_rejected"
    )
    assert dispatch_record.exc_info is None
    assert dispatch_record.local_order_id == str(order.id)
    assert provider_url not in caplog.text
    assert provider_token not in caplog.text
    assert provider_body not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [408, 409, 418, 425, 429, 500, 502, 503, 504],
)
async def test_alipos_create_order_ambiguous_http_status_is_unknown(status_code):
    response = httpx.Response(
        status_code,
        json={"detail": "customer-secret"},
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
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

    client.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"orderId": None}, {"orderId": "not-a-uuid"}],
)
async def test_alipos_create_order_invalid_success_identifier_is_unknown(payload):
    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
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

    client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_cash_alipos_rejected_marks_submission_failed_without_secret(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    response = httpx.Response(
        400,
        json={"detail": "customer-secret"},
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

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
            "app.services.alipos_api._get_token", new=AsyncMock(return_value="token")
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        caplog.at_level("INFO", logger="app.services.order_service"),
    ):
        with pytest.raises(OrderSubmissionRejected):
            await create_customer_order(db_session, user, _body())

    result = await db_session.execute(select(Order).where(Order.user_id == user.telegram_id))
    order = result.scalar_one()
    assert order.alipos_sync_error == "AliPOS rejected the order (HTTP 400)"
    assert order.status == "SUBMISSION_FAILED"
    assert "alipos_submit_rejected" in caplog.text
    assert "customer-secret" not in caplog.text


@pytest.mark.asyncio
async def test_paid_definite_submission_rejection_dispatches_one_refund(db_session):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=AsyncMock(side_effect=alipos_api.AliPOSRejected(400)),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        with pytest.raises(OrderSubmissionRejected):
            await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    refund.assert_awaited_once_with("payment-uuid")
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_paid_alipos_ambiguous_http_response_does_not_refund(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    response = httpx.Response(
        502,
        json={"detail": "provider-secret"},
        request=httpx.Request("POST", "https://alipos.example/order"),
    )
    request = AsyncMock(return_value=response)
    client = Mock()
    client.request = request
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
        caplog.at_level("INFO"),
    ):
        await _submit_queued_alipos_order(db_session, order.id)
        assert await _submit_queued_alipos_order(db_session, order.id) is None

    await db_session.refresh(order)
    request.assert_awaited_once()
    refund.assert_not_awaited()
    assert order.status == "SYNC_UNKNOWN"
    assert order.alipos_sync_status == "unknown"
    assert order.payment_status == "paid"
    assert order.refund_sync_status is None
    assert "provider-secret" not in caplog.text


@pytest.mark.asyncio
async def test_definite_rejection_with_ambiguous_refund_never_repeats_mutations(
    db_session,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    create = AsyncMock(side_effect=alipos_api.AliPOSRejected(400))
    refund = AsyncMock(
        side_effect=multicard_api.RefundOutcomeUnknown(
            "Multicard refund outcome is unknown"
        )
    )

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        with pytest.raises(OrderSubmissionRejected):
            await _submit_queued_alipos_order(db_session, order.id)
        assert await _submit_queued_alipos_order(db_session, order.id) is None

    await db_session.refresh(order)
    create.assert_awaited_once()
    refund.assert_awaited_once_with("payment-uuid")
    assert order.alipos_sync_status == "failed"
    assert order.status == "SUBMISSION_FAILED"
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "unknown"


@pytest.mark.asyncio
async def test_paid_token_failure_is_definite_sanitized_and_refunded_once(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    token_request = httpx.Request("POST", "https://alipos.example/oauth/token")
    token_response = httpx.Response(
        401,
        json={"detail": "customer-secret"},
        request=token_request,
    )
    token_error = httpx.HTTPStatusError(
        "token rejected",
        request=token_request,
        response=token_response,
    )
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(side_effect=token_error),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient") as client_factory,
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
        caplog.at_level("INFO"),
    ):
        with pytest.raises(OrderSubmissionRejected) as exc:
            await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    expected = "AliPOS order submission prerequisite failed (HTTP 401)"
    assert str(exc.value) == expected
    assert order.alipos_sync_error == expected
    assert order.alipos_sync_status == "failed"
    assert order.status == "SUBMISSION_FAILED"
    refund.assert_awaited_once_with("payment-uuid")
    client_factory.assert_not_called()
    assert "customer-secret" not in caplog.text


@pytest.mark.asyncio
async def test_paid_payment_method_lookup_error_is_sanitized_and_refunded_once(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    response = httpx.Response(
        400,
        json={"detail": "customer-secret"},
        request=httpx.Request("GET", "https://alipos.example/payment-methods"),
    )
    request = AsyncMock(return_value=response)
    client = Mock()
    client.request = request
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    refund = AsyncMock()

    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
        caplog.at_level("INFO"),
    ):
        with pytest.raises(OrderSubmissionRejected) as exc:
            await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    expected = "AliPOS order submission prerequisite failed (HTTP 400)"
    assert str(exc.value) == expected
    assert order.alipos_sync_error == expected
    assert order.alipos_sync_status == "failed"
    assert order.status == "SUBMISSION_FAILED"
    refund.assert_awaited_once_with("payment-uuid")
    request.assert_awaited_once()
    assert "customer-secret" not in caplog.text


@pytest.mark.asyncio
async def test_paid_payload_build_failure_is_sanitized_and_dispatches_one_refund(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    refund = AsyncMock()
    arbitrary_error = "payload-secret-" + "x" * 200

    with (
        patch(
            "app.services.order_service._build_alipos_payload",
            new=AsyncMock(side_effect=RuntimeError(arbitrary_error)),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
        caplog.at_level("INFO", logger="app.services.order_service"),
    ):
        with pytest.raises(OrderSubmissionRejected) as exc_info:
            await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    refund.assert_awaited_once_with("payment-uuid")
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"
    assert order.alipos_sync_error == "AliPOS order payload could not be prepared"
    assert str(exc_info.value) == "AliPOS order payload could not be prepared"
    assert arbitrary_error not in caplog.text
    assert arbitrary_error not in order.alipos_sync_error


@pytest.mark.asyncio
async def test_paid_invalid_alipos_response_is_unknown_without_refund(db_session):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=AsyncMock(return_value={"result": "OK"}),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    refund.assert_not_awaited()
    assert order.payment_status == "paid"
    assert order.refund_sync_status is None
    assert order.alipos_sync_status == "unknown"
    assert order.status == "SYNC_UNKNOWN"
    assert order.alipos_sync_error == "AliPOS order create outcome is unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payment_method", "payment_status"),
    [("cash", None), ("rahmat", "pending")],
)
async def test_cash_or_unpaid_submission_rejection_does_not_refund(
    db_session,
    payment_method,
    payment_status,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method=payment_method,
        payment_status=payment_status,
    )
    payment_id = CASH_PAYMENT_ID if payment_method == "cash" else ONLINE_PAYMENT_ID
    payment_title = "Наличные" if payment_method == "cash" else "online-order"
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(return_value=[{"id": payment_id, "title": payment_title}]),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=AsyncMock(side_effect=alipos_api.AliPOSRejected(400)),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        with pytest.raises(OrderSubmissionRejected):
            await submit_order_to_alipos(db_session, order)

    await db_session.refresh(order)
    refund.assert_not_awaited()
    assert order.payment_status == payment_status
    assert order.refund_sync_status is None


@pytest.mark.asyncio
async def test_paid_unknown_alipos_outcome_does_not_refund(db_session, caplog):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    create = AsyncMock(
        side_effect=alipos_api.AliPOSUnknownOutcome(
            "AliPOS order create outcome is unknown"
        )
    )
    refund = AsyncMock()

    with (
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(
                return_value=[{"id": ONLINE_PAYMENT_ID, "title": "online-order"}]
            ),
        ),
        patch(
            "app.services.order_service.alipos_api.create_order",
            new=create,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
        caplog.at_level("INFO", logger="app.services.order_service"),
    ):
        await _submit_queued_alipos_order(db_session, order.id)
        assert await _submit_queued_alipos_order(db_session, order.id) is None

    await db_session.refresh(order)
    create.assert_awaited_once()
    refund.assert_not_awaited()
    assert order.payment_status == "paid"
    assert order.refund_sync_status is None
    assert order.alipos_sync_status == "unknown"
    assert order.status == "SYNC_UNKNOWN"
    assert "alipos_submit_unknown" in caplog.text


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
