import asyncio
import datetime
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import main as app_main
from app.config import settings
from app.main import app
from app.models.models import Order, User
from app.schemas.order import OrderCreate
from app.services import alipos_api, multicard_api, order_service
from app.services.menu_catalog_service import PricedCart
from app.services.order_service import (
    CustomerOrderError,
    OrderSubmissionRejected,
    PhoneVerificationRequired,
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
from app.services.phone_verification_service import (
    InvalidPhoneNumber,
    phone_verification_fingerprint,
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
    manual_code="12",
)


@pytest_asyncio.fixture
async def refund_sessions(db_session):
    _ = db_session  # Ensure the schema exists before opening independent connections.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_user_ids: list[int] = []
    try:
        yield sessions, created_user_ids
    finally:
        if created_user_ids:
            async with sessions() as cleanup_db:
                await cleanup_db.execute(
                    delete(Order).where(Order.user_id.in_(created_user_ids))
                )
                await cleanup_db.execute(
                    delete(User).where(User.telegram_id.in_(created_user_ids))
                )
                await cleanup_db.commit()
        await engine.dispose()


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
        payment_method=payment_method,
        discriminator="delivery",
        delivery_address="Yakkasaray District, Shota Rustaveli 45",
        latitude="41.2995",
        longitude="69.2401",
    )


def _mark_phone_verified(user: User, phone_number: str | None = None) -> User:
    canonical_phone = phone_number or user.phone_number or "+998901112233"
    verified_at = datetime.datetime.now(datetime.UTC)
    user.phone_number = canonical_phone
    user.phone_verified_at = verified_at
    user.phone_verified_fingerprint = phone_verification_fingerprint(
        user.telegram_id,
        canonical_phone,
    )
    user.phone_verified_message_at = verified_at
    user.phone_verified_update_id = 1
    return user


async def _customer(db_session) -> User:
    user = _mark_phone_verified(
        User(
            telegram_id=7301,
            first_name="Customer",
            last_name=None,
            username=None,
            phone_number="+998901112233",
        )
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("discriminator", "payment_method"),
    [("delivery", "rahmat"), ("inplace", "rahmat")],
)
async def test_unverified_new_order_is_rejected_before_any_side_effect(
    db_session,
    discriminator,
    payment_method,
):
    user = User(
        telegram_id=7390 if discriminator == "delivery" else 7391,
        first_name="Unverified",
        last_name=None,
        username=None,
        phone_number="+998901112233",
    )
    db_session.add(user)
    await db_session.commit()
    body = (
        _delivery_body(payment_method)
        if discriminator == "delivery"
        else _body(payment_method)
    )
    price = AsyncMock(return_value=PRICED_CART)
    resolve_table = AsyncMock(return_value=TABLE)
    create_order = AsyncMock(return_value={"orderId": str(uuid.uuid4())})
    create_invoice = AsyncMock(
        return_value={
            "uuid": str(uuid.uuid4()),
            "checkout_url": "https://pay.example/checkout",
        }
    )
    payment_capability = Mock(return_value=True)

    with (
        patch("app.services.order_service.price_cart", new=price),
        patch(
            "app.services.order_service.can_use_inplace_online_payment",
            new=payment_capability,
        ),
        patch(
            "app.services.order_service.table_access.resolve_access_token",
            new=resolve_table,
        ),
        patch(
            "app.services.order_service.alipos_api.get_payment_methods",
            new=AsyncMock(return_value=[{"id": CASH_PAYMENT_ID, "title": "cash"}]),
        ),
        patch("app.services.order_service.alipos_api.create_order", new=create_order),
        patch(
            "app.services.order_service.multicard_api.create_invoice",
            new=create_invoice,
        ),
    ):
        with pytest.raises(PhoneVerificationRequired):
            await create_customer_order(db_session, user, body)

    price.assert_not_awaited()
    payment_capability.assert_not_called()
    resolve_table.assert_not_awaited()
    create_order.assert_not_awaited()
    create_invoice.assert_not_awaited()
    result = await db_session.execute(
        select(Order).where(Order.user_id == user.telegram_id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_idempotent_replay_precedes_current_phone_verification(db_session):
    user = User(
        telegram_id=7392,
        first_name="Changed profile",
        last_name=None,
        username=None,
        phone_number="+998901112233",
    )
    request_id = uuid.uuid4()
    existing = Order(
        user_id=user.telegram_id,
        client_request_id=request_id,
        items=[],
        delivery_info={"clientName": "Original", "phoneNumber": "+998901112233"},
        items_cost=10000,
        total_amount=10000,
        delivery_fee=0,
        comment="Original note",
        payment_method="cash",
        discriminator="inplace",
        table_id=TABLE_ID,
        alipos_eats_id=f"replay-{uuid.uuid4().hex}",
        alipos_sync_status="synced",
        status="NEW",
    )
    db_session.add_all([user, existing])
    await db_session.commit()
    price = AsyncMock(return_value=PRICED_CART)

    with patch("app.services.order_service.price_cart", new=price):
        replayed = await create_customer_order(
            db_session,
            user,
            _body(client_request_id=request_id),
        )

    assert replayed.id == existing.id
    assert replayed.delivery_info == existing.delivery_info
    price.assert_not_awaited()


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
    assert order.delivery_info == {
        "clientName": "Customer",
        "phoneNumber": "+998901112233",
    }
    assert order.contact_phone_verified is True
    assert order.comment == "Iltimos, piyozsiz"
    assert payload["deliveryInfo"] == order.delivery_info
    assert "contact_phone_verified" not in payload["deliveryInfo"]
    assert payload["comment"] == "Tel: +998 90 *** 2233\nIltimos, piyozsiz"

    _mark_phone_verified(user, "+998907654321")
    await db_session.commit()
    await db_session.refresh(order)
    with patch(
        "app.services.order_service.resolve_payment_method_id",
        new=AsyncMock(return_value=CASH_PAYMENT_ID),
    ):
        rebuilt_payload = await order_service._build_alipos_payload(order)

    assert order.delivery_info["phoneNumber"] == "+998901112233"
    assert rebuilt_payload["deliveryInfo"]["phoneNumber"] == "+998901112233"
    assert rebuilt_payload["comment"] == "Tel: +998 90 *** 2233\nIltimos, piyozsiz"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phone_number", "note", "expected_comment"),
    [
        ("+998901234567", None, "Tel: +998 90 *** 4567"),
        ("+998901234567", "", "Tel: +998 90 *** 4567"),
        (
            "+15551234567",
            "  Keep exact spacing  ",
            "Tel: +155 **** 4567\n  Keep exact spacing  ",
        ),
    ],
)
async def test_verified_snapshot_composes_masked_alipos_comment_without_mutation(
    phone_number,
    note,
    expected_comment,
):
    order = Order(
        items=PRICED_CART.items,
        delivery_info={"clientName": "Customer", "phoneNumber": phone_number},
        items_cost=36000,
        total_amount=36000,
        delivery_fee=0,
        comment=note,
        contact_phone_verified=True,
        payment_method="cash",
        discriminator="delivery",
        alipos_eats_id="stable-eats-id",
    )

    with patch(
        "app.services.order_service.resolve_payment_method_id",
        new=AsyncMock(return_value=CASH_PAYMENT_ID),
    ):
        payload = await order_service._build_alipos_payload(order)

    assert payload["deliveryInfo"] == {
        "clientName": "Customer",
        "phoneNumber": phone_number,
    }
    assert "contact_phone_verified" not in payload["deliveryInfo"]
    assert payload["comment"] == expected_comment
    assert order.comment == note


@pytest.mark.asyncio
async def test_unverified_legacy_snapshot_keeps_historical_alipos_comment():
    order = Order(
        items=PRICED_CART.items,
        delivery_info={
            "clientName": "Legacy customer",
            "phoneNumber": "+998901234567",
        },
        items_cost=36000,
        total_amount=36000,
        delivery_fee=0,
        comment="Legacy note",
        contact_phone_verified=False,
        payment_method="cash",
        discriminator="delivery",
        alipos_eats_id="legacy-eats-id",
    )

    with patch(
        "app.services.order_service.resolve_payment_method_id",
        new=AsyncMock(return_value=CASH_PAYMENT_ID),
    ):
        payload = await order_service._build_alipos_payload(order)

    assert payload["comment"] == "Legacy note"
    assert order.comment == "Legacy note"


@pytest.mark.asyncio
async def test_corrupt_verified_snapshot_fails_alipos_payload_build_closed():
    order = Order(
        items=PRICED_CART.items,
        delivery_info={"clientName": "Customer", "phoneNumber": "not-canonical"},
        items_cost=36000,
        total_amount=36000,
        delivery_fee=0,
        comment="Customer note",
        contact_phone_verified=True,
        payment_method="cash",
        discriminator="delivery",
        alipos_eats_id="corrupt-eats-id",
    )

    with (
        patch(
            "app.services.order_service.resolve_payment_method_id",
            new=AsyncMock(return_value=CASH_PAYMENT_ID),
        ),
        pytest.raises(InvalidPhoneNumber),
    ):
        await order_service._build_alipos_payload(order)


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
    user = _mark_phone_verified(
        User(
            telegram_id=7302,
            first_name="Customer",
            last_name=None,
            username=None,
        )
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


async def _committed_refund_order(
    refund_sessions,
    *,
    refund_sync_status: str,
) -> tuple[uuid.UUID, str]:
    sessions, created_user_ids = refund_sessions
    user_id = 8_000_000_000 + uuid.uuid4().int % 1_000_000_000
    payment_uuid = f"refund-{uuid.uuid4()}"
    async with sessions() as db:
        user = User(
            telegram_id=user_id,
            first_name="Refund customer",
            last_name=None,
            username=None,
        )
        order = Order(
            user_id=user_id,
            items=[],
            delivery_info={
                "clientName": "Refund customer",
                "phoneNumber": "+998900000000",
            },
            items_cost=10000,
            total_amount=11000,
            delivery_fee=0,
            payment_method="rahmat",
            payment_provider="multicard",
            payment_status="refund_pending",
            multicard_payment_uuid=payment_uuid,
            refund_sync_status=refund_sync_status,
            discriminator="inplace",
            table_id=uuid.uuid4(),
            alipos_eats_id=f"refund-{uuid.uuid4().hex}",
            alipos_sync_status="failed",
            status="SUBMISSION_FAILED",
        )
        db.add_all([user, order])
        await db.commit()
        order_id = order.id
    created_user_ids.append(user_id)
    return order_id, payment_uuid


async def _committed_invoice_order(
    refund_sessions,
    *,
    payment_status: str,
    invoice_uuid: str | None = None,
) -> uuid.UUID:
    sessions, created_user_ids = refund_sessions
    user_id = 8_000_000_000 + uuid.uuid4().int % 1_000_000_000
    async with sessions() as db:
        user = User(
            telegram_id=user_id,
            first_name="Invoice customer",
            last_name=None,
            username=None,
        )
        order = Order(
            user_id=user_id,
            items=[],
            delivery_info={
                "clientName": "Invoice customer",
                "phoneNumber": "+998900000000",
            },
            items_cost=10000,
            total_amount=11000,
            delivery_fee=0,
            payment_method="rahmat",
            payment_provider="multicard",
            payment_status=payment_status,
            multicard_invoice_uuid=invoice_uuid,
            discriminator="inplace",
            table_id=uuid.uuid4(),
            alipos_eats_id=f"invoice-{uuid.uuid4().hex}",
            alipos_sync_status="awaiting_payment",
            status="PAYMENT_REVIEW",
        )
        db.add_all([user, order])
        await db.commit()
        order_id = order.id
    created_user_ids.append(user_id)
    return order_id


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
async def test_interrupted_alipos_send_preserves_advanced_webhook_status(db_session):
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
    order.status = "ACCEPTED_BY_RESTAURANT"
    order.order_number = "A-204"
    await db_session.commit()

    recovered = await recover_interrupted_alipos_orders(db_session)

    await db_session.refresh(order)
    assert recovered == 1
    assert order.alipos_sync_status == "unknown"
    assert order.status == "ACCEPTED_BY_RESTAURANT"
    assert order.order_number == "A-204"


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
async def test_invoice_ambiguous_outcome_blocks_retry_and_cash_switch(
    db_session,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="invoice_queued",
    )
    order.payment_provider = "multicard"
    order.alipos_sync_status = "awaiting_payment"
    order.status = "PAYMENT_REVIEW"
    await db_session.commit()
    create_invoice = AsyncMock(
        side_effect=multicard_api.InvoiceOutcomeUnknown("ambiguous-invoice")
    )
    cancel_invoice = AsyncMock()

    with (
        patch(
            "app.services.order_service.multicard_api.create_invoice",
            new=create_invoice,
        ),
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=cancel_invoice,
        ),
    ):
        await order_service._create_order_invoice(db_session, order)
        await order_service._create_order_invoice(db_session, order)
        with pytest.raises(order_service.PaymentRetryConflict):
            await order_service.retry_customer_order_payment(db_session, user, order.id)
        with pytest.raises(order_service.PaymentSwitchConflict):
            await order_service.switch_customer_order_to_cash(
                db_session,
                user,
                order.id,
            )

    await db_session.refresh(order)
    create_invoice.assert_awaited_once()
    cancel_invoice.assert_not_awaited()
    assert order.payment_status == "invoice_unknown"
    assert order.status == "PAYMENT_REVIEW"
    assert order.multicard_invoice_uuid == "ambiguous-invoice"
    assert order.multicard_checkout_url is None


@pytest.mark.asyncio
async def test_invoice_recovery_retries_only_never_attempted_rows(
    refund_sessions,
):
    sessions, _ = refund_sessions
    queued_id = await _committed_invoice_order(
        refund_sessions,
        payment_status="invoice_queued",
    )
    sending_id = await _committed_invoice_order(
        refund_sessions,
        payment_status="invoice_sending",
    )
    unknown_id = await _committed_invoice_order(
        refund_sessions,
        payment_status="invoice_unknown",
        invoice_uuid="unknown-invoice",
    )
    dispatch = AsyncMock()

    with (
        patch.object(order_service, "async_session", sessions),
        patch.object(order_service, "dispatch_queued_invoice", new=dispatch),
    ):
        await order_service.recover_invoice_operations()
        await asyncio.sleep(0)

    dispatch.assert_awaited_once_with(queued_id)
    async with sessions() as inspect_db:
        queued = await inspect_db.get(Order, queued_id)
        sending = await inspect_db.get(Order, sending_id)
        unknown = await inspect_db.get(Order, unknown_id)
        assert queued is not None
        assert sending is not None
        assert unknown is not None
        assert queued.payment_status == "invoice_queued"
        assert sending.payment_status == "invoice_unknown"
        assert sending.status == "PAYMENT_REVIEW"
        assert unknown.payment_status == "invoice_unknown"
        assert unknown.multicard_invoice_uuid == "unknown-invoice"


@pytest.mark.asyncio
async def test_malformed_invoice_success_with_uuid_preserves_reference_and_reconciles_by_get(
    db_session,
    monkeypatch,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="invoice_queued",
    )
    order.payment_provider = "multicard"
    order.alipos_sync_status = "awaiting_payment"
    order.status = "PAYMENT_REVIEW"
    await db_session.commit()
    monkeypatch.setattr(
        settings,
        "multicard_allow_uuidless_sandbox_checkout",
        False,
        raising=False,
    )
    invoice_uuid = "partial-invoice-uuid"
    post_response = httpx.Response(
        200,
        json={"success": True, "data": {"uuid": invoice_uuid}},
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    incomplete_get = httpx.Response(
        200,
        json={"success": True, "data": {"uuid": invoice_uuid}},
        request=httpx.Request(
            "GET", f"https://multicard.example/payment/invoice/{invoice_uuid}"
        ),
    )
    complete_get = httpx.Response(
        200,
        json={
            "success": True,
            "data": {
                "uuid": invoice_uuid,
                "checkout_url": "https://pay.example/partial-invoice",
            },
        },
        request=httpx.Request(
            "GET", f"https://multicard.example/payment/invoice/{invoice_uuid}"
        ),
    )
    failed_get_request = httpx.Request(
        "GET", f"https://multicard.example/payment/invoice/{invoice_uuid}"
    )
    client = _multicard_invoice_client(post_response)
    client.get = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("lookup timed out", request=failed_get_request),
            incomplete_get,
            complete_get,
        ]
    )

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        await order_service._create_order_invoice(db_session, order)
        await db_session.refresh(order)
        assert order.payment_status == "invoice_unknown"
        assert order.multicard_invoice_uuid == invoice_uuid

        assert await order_service.reconcile_unknown_invoices(db_session) == 0
        await db_session.refresh(order)
        assert order.payment_status == "invoice_unknown"
        assert order.multicard_invoice_uuid == invoice_uuid

        assert await order_service.reconcile_unknown_invoices(db_session) == 0
        await db_session.refresh(order)
        assert order.payment_status == "invoice_unknown"
        assert order.multicard_invoice_uuid == invoice_uuid

        assert await order_service.reconcile_unknown_invoices(db_session) == 1

    await db_session.refresh(order)
    client.post.assert_awaited_once()
    assert client.get.await_count == 3
    assert order.payment_status == "pending"
    assert order.status == "AWAITING_PAYMENT"
    assert order.multicard_invoice_uuid == invoice_uuid
    assert order.multicard_checkout_url == "https://pay.example/partial-invoice"


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
@pytest.mark.parametrize(
    "provider_error",
    [
        multicard_api.RefundNotAttempted("Multicard refund was not attempted"),
        multicard_api.RefundRejected(400),
        multicard_api.RefundOutcomeUnknown("Multicard refund outcome is unknown"),
    ],
    ids=["not-attempted", "rejected", "unknown"],
)
async def test_refund_terminal_state_cannot_be_downgraded_by_stale_dispatch_writer(
    refund_sessions,
    provider_error,
):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="queued",
    )

    async def terminal_callback_wins(_payment_uuid: str) -> None:
        async with sessions() as callback_db:
            await callback_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(
                    payment_status="refunded",
                    refund_sync_status="refunded",
                    refund_sync_error=None,
                    payment_error=None,
                )
            )
            await callback_db.commit()
        raise provider_error

    refund = AsyncMock(side_effect=terminal_callback_wins)
    with patch(
        "app.services.order_service.multicard_api.refund_payment",
        new=refund,
    ):
        async with sessions() as stale_dispatch_db:
            await _dispatch_queued_refund(stale_dispatch_db, order_id)

    refund.assert_awaited_once_with(payment_uuid)
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"
        assert persisted.refund_sync_error is None
        assert persisted.payment_error is None


@pytest.mark.asyncio
async def test_refund_terminal_state_cannot_be_downgraded_by_stale_reconciler(
    refund_sessions,
):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="unknown",
    )

    async def terminal_callback_wins(_payment_uuid: str) -> dict:
        async with sessions() as callback_db:
            await callback_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(
                    payment_status="refunded",
                    refund_sync_status="refunded",
                    refund_sync_error=None,
                    payment_error=None,
                )
            )
            await callback_db.commit()
        raise RuntimeError("unsafe provider reconciliation failure")

    lookup = AsyncMock(side_effect=terminal_callback_wins)
    with patch(
        "app.services.order_service.multicard_api.get_payment",
        new=lookup,
    ):
        async with sessions() as stale_reconcile_db:
            await reconcile_unknown_refunds(stale_reconcile_db)

    lookup.assert_awaited_once_with(payment_uuid)
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"
        assert persisted.refund_sync_error is None
        assert persisted.payment_error is None


@pytest.mark.asyncio
async def test_refund_reconciliation_provider_reads_run_outside_transactions(
    db_session,
):
    user = await _customer(db_session)
    orders = []
    for index in range(2):
        order = await _queued_order(
            db_session,
            user,
            payment_method="rahmat",
            payment_status="refund_pending",
        )
        order.refund_sync_status = "unknown"
        order.multicard_payment_uuid = f"payment-{index}"
        orders.append(order)
    await db_session.commit()
    transaction_states: list[bool] = []

    async def observe_transaction(_payment_uuid: str) -> dict[str, str]:
        transaction_states.append(db_session.in_transaction())
        return {"status": "revert"}

    with patch(
        "app.services.order_service.multicard_api.get_payment",
        new=AsyncMock(side_effect=observe_transaction),
    ):
        reconciled = await reconcile_unknown_refunds(db_session)

    assert reconciled == 2
    assert transaction_states == [False, False]
    for order in orders:
        await db_session.refresh(order)
        assert order.payment_status == "refunded"
        assert order.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_runtime_unknown_refund_is_reconciled_without_restart(refund_sessions):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="unknown",
    )
    lookup = AsyncMock(return_value={"status": "revert"})

    with (
        patch.object(order_service, "async_session", sessions),
        patch(
            "app.services.order_service.multicard_api.get_payment",
            new=lookup,
        ),
    ):
        await order_service.reconcile_provider_operations()

    lookup.assert_awaited_once_with(payment_uuid)
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_runtime_unknown_invoice_is_reconciled_without_repeating_post(
    refund_sessions,
):
    sessions, _ = refund_sessions
    invoice_uuid = f"invoice-{uuid.uuid4()}"
    order_id = await _committed_invoice_order(
        refund_sessions,
        payment_status="invoice_unknown",
        invoice_uuid=invoice_uuid,
    )
    lookup = AsyncMock(
        return_value={
            "uuid": invoice_uuid,
            "checkout_url": "https://pay.example/runtime-invoice",
        }
    )
    create = AsyncMock()

    with (
        patch.object(order_service, "async_session", sessions),
        patch(
            "app.services.order_service.multicard_api.get_invoice",
            new=lookup,
        ),
        patch(
            "app.services.order_service.multicard_api.create_invoice",
            new=create,
        ),
    ):
        await order_service.reconcile_provider_operations()

    lookup.assert_awaited_once_with(invoice_uuid)
    create.assert_not_awaited()
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "pending"
        assert persisted.status == "AWAITING_PAYMENT"
        assert persisted.multicard_checkout_url == (
            "https://pay.example/runtime-invoice"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_stage",
    ["token", "client-construction", "client-entry"],
)
async def test_pre_delete_refund_failure_is_retried_once_at_runtime(
    refund_sessions,
    caplog,
    failure_stage,
):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="queued",
    )
    provider_url_canary = "https://provider-secret.example"
    credential_canary = "credential-canary-4721"
    response_body_canary = "response-body-canary-8036"
    unsafe_chain_canary = "unsafe-chain-canary-1954"
    try:
        try:
            raise RuntimeError(unsafe_chain_canary)
        except RuntimeError as exc:
            raise RuntimeError(
                f"auth failed at {provider_url_canary} for {payment_uuid} "
                f"with {credential_canary}: {response_body_canary}"
            ) from exc
    except RuntimeError as exc:
        unsafe_setup_error = exc

    marker_states: list[tuple[str | None, str | None]] = []

    async def observe_committed_marker(*_args, **_kwargs) -> httpx.Response:
        async with sessions() as inspect_db:
            persisted = await inspect_db.get(Order, order_id)
            assert persisted is not None
            marker_states.append(
                (persisted.payment_status, persisted.refund_sync_status)
            )
        return httpx.Response(
            200,
            json={"success": True, "data": {"status": "revert"}},
            request=httpx.Request(
                "DELETE",
                f"{provider_url_canary}/payment/{payment_uuid}",
            ),
        )

    client = Mock()
    client.delete = AsyncMock(side_effect=observe_committed_marker)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    get_token = AsyncMock(return_value="safe-token")
    client_factory = Mock(return_value=client)
    failed_client = None
    if failure_stage == "token":
        get_token.side_effect = [unsafe_setup_error, "safe-token"]
    elif failure_stage == "client-construction":
        client_factory.side_effect = [unsafe_setup_error, client]
    else:
        failed_client = Mock()
        failed_client.delete = AsyncMock()
        failed_client.__aenter__ = AsyncMock(side_effect=unsafe_setup_error)
        failed_client.__aexit__ = AsyncMock(return_value=None)
        client_factory.side_effect = [failed_client, client]
    provider_lookup = AsyncMock(return_value={"status": "success"})
    original_refund = multicard_api.refund_payment
    captured_errors: list[Exception] = []

    async def capture_sanitized_error(refund_uuid: str) -> dict:
        try:
            return await original_refund(refund_uuid)
        except Exception as exc:
            captured_errors.append(exc)
            raise

    with (
        patch.object(order_service, "async_session", sessions),
        patch("app.services.multicard_api._get_token", new=get_token),
        patch("app.services.multicard_api.httpx.AsyncClient", new=client_factory),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=capture_sanitized_error,
        ),
        patch(
            "app.services.order_service.multicard_api.get_payment",
            new=provider_lookup,
        ),
        caplog.at_level("WARNING", logger="app.services.order_service"),
    ):
        async with sessions() as dispatch_db:
            await _dispatch_queued_refund(dispatch_db, order_id)

        client.delete.assert_not_awaited()
        if failed_client is not None:
            failed_client.delete.assert_not_awaited()
        async with sessions() as inspect_db:
            retryable = await inspect_db.get(Order, order_id)
            assert retryable is not None
            assert retryable.payment_status == "refund_pending"
            assert retryable.refund_sync_status == "queued"

        await order_service.reconcile_provider_operations()

    assert get_token.await_count == 2
    client.delete.assert_awaited_once()
    provider_lookup.assert_not_awaited()
    assert marker_states == [("refund_pending", "sending")]
    assert len(captured_errors) == 1
    safe_error = captured_errors[0]
    assert isinstance(safe_error, multicard_api.RefundNotAttempted)
    assert safe_error.__cause__ is None
    assert safe_error.__suppress_context__ is True

    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"

    for secret in (
        provider_url_canary,
        credential_canary,
        payment_uuid,
        response_body_canary,
        unsafe_chain_canary,
    ):
        assert secret not in str(safe_error)
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_reconciler_race_does_not_strand_pre_delete_refund(refund_sessions):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="queued",
    )
    token_started = asyncio.Event()
    release_token_failure = asyncio.Event()
    token_calls = 0

    async def fail_first_token_attempt() -> str:
        nonlocal token_calls
        token_calls += 1
        if token_calls == 1:
            token_started.set()
            await release_token_failure.wait()
            raise RuntimeError("unsafe blocked token failure")
        return "safe-token"

    marker_states: list[tuple[str | None, str | None]] = []

    async def observe_committed_marker(*_args, **_kwargs) -> httpx.Response:
        async with sessions() as inspect_db:
            persisted = await inspect_db.get(Order, order_id)
            assert persisted is not None
            marker_states.append(
                (persisted.payment_status, persisted.refund_sync_status)
            )
        return httpx.Response(
            200,
            json={"success": True, "data": {"status": "revert"}},
            request=httpx.Request(
                "DELETE",
                f"https://provider.example/payment/{payment_uuid}",
            ),
        )

    client = Mock()
    client.delete = AsyncMock(side_effect=observe_committed_marker)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    provider_lookup = AsyncMock(return_value={"status": "success"})

    async def run_first_dispatch() -> None:
        async with sessions() as dispatch_db:
            await _dispatch_queued_refund(dispatch_db, order_id)

    with (
        patch.object(order_service, "async_session", sessions),
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(side_effect=fail_first_token_attempt),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
        patch(
            "app.services.order_service.multicard_api.get_payment",
            new=provider_lookup,
        ),
    ):
        dispatch_task = asyncio.create_task(run_first_dispatch())
        await asyncio.wait_for(token_started.wait(), timeout=1)
        try:
            async with sessions() as inspect_db:
                sending = await inspect_db.get(Order, order_id)
                assert sending is not None
                assert sending.refund_sync_status == "sending"

            async with sessions() as reconcile_db:
                reconciled = await reconcile_unknown_refunds(reconcile_db)
            assert reconciled == 0
            async with sessions() as inspect_db:
                raced = await inspect_db.get(Order, order_id)
                assert raced is not None
                assert raced.refund_sync_status == "unknown"
        finally:
            release_token_failure.set()
            await dispatch_task

        async with sessions() as inspect_db:
            retryable = await inspect_db.get(Order, order_id)
            assert retryable is not None
            assert retryable.payment_status == "refund_pending"
            assert retryable.refund_sync_status == "queued"

        await order_service.reconcile_provider_operations()

    assert token_calls == 2
    provider_lookup.assert_awaited_once_with(payment_uuid)
    client.delete.assert_awaited_once()
    assert marker_states == [("refund_pending", "sending")]
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_refund_context_exit_failure_stays_unknown_and_get_only(
    refund_sessions,
):
    sessions, _ = refund_sessions
    order_id, payment_uuid = await _committed_refund_order(
        refund_sessions,
        refund_sync_status="queued",
    )
    response = httpx.Response(
        200,
        json={"success": True, "data": {"status": "revert"}},
        request=httpx.Request(
            "DELETE",
            "https://provider.example/payment/context-exit",
        ),
    )
    client = Mock()
    client.delete = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(
        side_effect=RuntimeError("unsafe context exit failure")
    )
    provider_lookup = AsyncMock(return_value={"status": "success"})

    with (
        patch.object(order_service, "async_session", sessions),
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="safe-token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
        patch(
            "app.services.order_service.multicard_api.get_payment",
            new=provider_lookup,
        ),
    ):
        async with sessions() as dispatch_db:
            await _dispatch_queued_refund(dispatch_db, order_id)
        await order_service.reconcile_provider_operations()

    client.delete.assert_awaited_once()
    provider_lookup.assert_awaited_once_with(payment_uuid)
    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.payment_status == "refund_pending"
        assert persisted.refund_sync_status == "unknown"


@pytest.mark.asyncio
async def test_refund_error_log_excludes_payment_uuid_and_provider_url(
    db_session,
    caplog,
):
    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="refund_pending",
    )
    payment_uuid = "refund-canary-2f0de170"
    credential_canary = "credential-canary-91a3"
    order.refund_sync_status = "queued"
    order.multicard_payment_uuid = payment_uuid
    await db_session.commit()

    unsafe_url = f"https://provider-secret.example/payment/{payment_uuid}"
    request = httpx.Request(
        "DELETE",
        unsafe_url,
        headers={"Authorization": f"Bearer {credential_canary}"},
    )
    client = Mock()
    client.delete = AsyncMock(
        side_effect=httpx.ReadTimeout(
            f"raw response details at {unsafe_url} using {credential_canary}",
            request=request,
        )
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    original_refund = multicard_api.refund_payment
    captured_error: dict[str, Exception] = {}

    async def capture_safe_refund_error(refund_uuid: str) -> dict:
        try:
            return await original_refund(refund_uuid)
        except Exception as exc:
            captured_error["error"] = exc
            raise

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=capture_safe_refund_error,
        ),
        caplog.at_level("WARNING", logger="app.services.order_service"),
    ):
        await _dispatch_queued_refund(db_session, order.id)

    assert client.delete.await_count == 1
    error = captured_error["error"]
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert payment_uuid not in caplog.text
    assert "/payment/" not in caplog.text
    assert "raw response details" not in caplog.text
    assert credential_canary not in caplog.text


@pytest.mark.asyncio
async def test_provider_reconciliation_loop_runs_after_startup_survives_tick_error_and_stops_on_shutdown(
    refund_sessions,
    monkeypatch,
    caplog,
):
    sessions, created_user_ids = refund_sessions
    real_reconcile = order_service.reconcile_provider_operations
    first_tick_failed = asyncio.Event()
    tick_count = 0
    log_canary = "tick-secret-/payment/refund-canary-4421"

    async def flaky_reconcile() -> tuple[int, int]:
        nonlocal tick_count
        tick_count += 1
        if tick_count == 1:
            first_tick_failed.set()
            raise RuntimeError(log_canary)
        return await real_reconcile()

    monkeypatch.setattr(order_service, "async_session", sessions)
    monkeypatch.setattr(order_service, "reconcile_provider_operations", flaky_reconcile)
    monkeypatch.setattr(
        order_service,
        "recover_queued_alipos_orders",
        AsyncMock(),
    )
    monkeypatch.setattr(order_service, "recover_refund_operations", AsyncMock())
    monkeypatch.setattr(app_main, "_expire_pending_payments", AsyncMock())
    monkeypatch.setattr(settings, "provider_reconciliation_interval_seconds", 0.01)
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "public_backend_url", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    refund_lookup = AsyncMock(return_value={"status": "revert"})
    cancel_lookup = AsyncMock(return_value={"status": "CANCELLED"})
    refund_delete = AsyncMock()
    cancel_delete = AsyncMock()
    task = None
    with (
        patch(
            "app.services.order_service.multicard_api.get_payment",
            new=refund_lookup,
        ),
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=cancel_lookup,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund_delete,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel_delete,
        ),
        caplog.at_level("WARNING", logger="app.main"),
    ):
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(first_tick_failed.wait(), timeout=1)
            task = app.state.provider_reconciliation_task

            user_id = 8_000_000_000 + uuid.uuid4().int % 1_000_000_000
            refund_payment_uuid = f"refund-{uuid.uuid4()}"
            cancel_provider_id = uuid.uuid4()
            async with sessions() as seed_db:
                user = User(
                    telegram_id=user_id,
                    first_name="Runtime reconciliation customer",
                    last_name=None,
                    username=None,
                )
                refund_order = Order(
                    user_id=user_id,
                    items=[],
                    delivery_info={},
                    items_cost=10000,
                    total_amount=11000,
                    delivery_fee=0,
                    payment_method="rahmat",
                    payment_provider="multicard",
                    payment_status="refund_pending",
                    multicard_payment_uuid=refund_payment_uuid,
                    refund_sync_status="unknown",
                    discriminator="inplace",
                    table_id=uuid.uuid4(),
                    alipos_eats_id=f"runtime-refund-{uuid.uuid4().hex}",
                    alipos_sync_status="failed",
                    status="SUBMISSION_FAILED",
                )
                cancel_order = Order(
                    user_id=user_id,
                    items=[],
                    delivery_info={},
                    items_cost=10000,
                    total_amount=11000,
                    delivery_fee=0,
                    payment_method="cash",
                    discriminator="inplace",
                    table_id=uuid.uuid4(),
                    alipos_order_id=cancel_provider_id,
                    alipos_eats_id=f"runtime-cancel-{uuid.uuid4().hex}",
                    alipos_sync_status="synced",
                    alipos_cancel_status="unknown",
                    cancel_requested_at=datetime.datetime.now(datetime.UTC).replace(
                        tzinfo=None
                    ),
                    status="NEW",
                )
                seed_db.add_all([user, refund_order, cancel_order])
                await seed_db.commit()
                refund_order_id = refund_order.id
                cancel_order_id = cancel_order.id
            created_user_ids.append(user_id)

            deadline = asyncio.get_running_loop().time() + 2
            while True:
                async with sessions() as inspect_db:
                    persisted_refund = await inspect_db.get(Order, refund_order_id)
                    persisted_cancel = await inspect_db.get(Order, cancel_order_id)
                    if (
                        persisted_refund is not None
                        and persisted_refund.payment_status == "refunded"
                        and persisted_refund.refund_sync_status == "refunded"
                        and persisted_cancel is not None
                        and persisted_cancel.status == "CANCELLED"
                        and persisted_cancel.alipos_cancel_status == "cancelled"
                    ):
                        break
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail("runtime provider reconciliation did not complete")
                await asyncio.sleep(0.01)

    assert tick_count >= 2
    assert task is not None
    assert task.done()
    assert getattr(app.state, "provider_reconciliation_task", None) is None
    assert "provider_reconciliation_tick_failed" in caplog.text
    assert log_canary not in caplog.text
    refund_lookup.assert_awaited_once_with(refund_payment_uuid)
    cancel_lookup.assert_awaited_once_with(str(cancel_provider_id))
    refund_delete.assert_not_awaited()
    cancel_delete.assert_not_awaited()


def _multicard_invoice_client(response: httpx.Response) -> Mock:
    client = Mock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_invoice_http_503_is_outcome_unknown():
    response = httpx.Response(
        503,
        json={"success": False, "error": {"code": "ERROR_UNKNOWN"}},
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceOutcomeUnknown):
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_uuid"),
    [
        (
            httpx.Response(
                200,
                content=b"not-json",
                request=httpx.Request(
                    "POST", "https://multicard.example/payment/invoice"
                ),
            ),
            None,
        ),
        (
            httpx.Response(
                200,
                json={"success": True, "data": {"uuid": "invoice-uuid"}},
                request=httpx.Request(
                    "POST", "https://multicard.example/payment/invoice"
                ),
            ),
            "invoice-uuid",
        ),
        (
            httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"checkout_url": "https://pay.example/checkout"},
                },
                request=httpx.Request(
                    "POST", "https://multicard.example/payment/invoice"
                ),
            ),
            None,
        ),
    ],
    ids=["malformed-json", "missing-checkout", "missing-uuid"],
)
async def test_incomplete_invoice_success_is_unknown_and_preserves_uuid(
    response,
    expected_uuid,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "multicard_allow_uuidless_sandbox_checkout",
        False,
        raising=False,
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceOutcomeUnknown) as exc_info:
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    assert exc_info.value.invoice_uuid == expected_uuid
    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_uuidless", [False, True])
@pytest.mark.parametrize(
    "uuid_value",
    [42, True, {"value": "invoice-uuid"}, ["invoice-uuid"]],
    ids=["integer", "boolean", "object", "array"],
)
async def test_wrong_typed_invoice_uuid_is_unknown_even_with_uuidless_opt_in(
    uuid_value,
    allow_uuidless,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "multicard_allow_uuidless_sandbox_checkout",
        allow_uuidless,
    )
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {
                "uuid": uuid_value,
                "checkout_url": "https://pay.example/checkout",
            },
        },
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceOutcomeUnknown) as exc_info:
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    assert exc_info.value.invoice_uuid is None
    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("uuid_value", ["", "   "], ids=["empty", "whitespace"])
async def test_empty_string_invoice_uuid_is_not_uuidless_sandbox_checkout(
    uuid_value,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "multicard_allow_uuidless_sandbox_checkout",
        True,
    )
    response = httpx.Response(
        200,
        json={
            "success": True,
            "data": {
                "uuid": uuid_value,
                "checkout_url": "https://pay.example/checkout",
            },
        },
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceOutcomeUnknown):
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(400, "ERROR_FIELDS"), (404, "ERROR_NOT_FOUND")],
)
async def test_invoice_exact_documented_rejection_pairs_are_definite(
    status_code,
    error_code,
):
    response = httpx.Response(
        status_code,
        json={
            "success": False,
            "error": {"code": error_code, "details": "provider-secret"},
        },
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceRejected) as exc_info:
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    assert exc_info.value.status_code == status_code
    assert "provider-secret" not in str(exc_info.value)
    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (400, "ERROR_NOT_FOUND"),
        (404, "ERROR_FIELDS"),
        (409, "ERROR_FIELDS"),
        (400, "ERROR_UNKNOWN"),
        (408, "ERROR_CALLBACK_TIMEOUT"),
        (425, "ERROR_DEBIT_UNKNOWN"),
        (429, "ERROR_FIELDS"),
    ],
)
async def test_invoice_unlisted_4xx_pairs_are_unknown(status_code, error_code):
    response = httpx.Response(
        status_code,
        json={
            "success": False,
            "error": {"code": error_code, "details": "provider-secret"},
        },
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceOutcomeUnknown):
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_invoice_token_failure_is_sanitized_and_not_attempted():
    post = AsyncMock()
    client = Mock()
    client.post = post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(side_effect=RuntimeError("credential-canary")),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoicePreSubmitError) as exc_info:
            await multicard_api.create_invoice(
                amount_tiyin=100_000,
                invoice_id="order-123",
                return_url="https://app.example/order-123",
            )

    assert "credential-canary" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_uuidless_legacy_checkout_requires_explicit_flag(monkeypatch):
    monkeypatch.setattr(
        settings,
        "multicard_allow_uuidless_sandbox_checkout",
        True,
        raising=False,
    )
    response = httpx.Response(
        200,
        json={"success": True, "data": {"uuid": None}},
        request=httpx.Request("POST", "https://multicard.example/payment/invoice"),
    )
    client = _multicard_invoice_client(response)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        invoice = await multicard_api.create_invoice(
            amount_tiyin=100_000,
            invoice_id="order-123",
            return_url="https://app.example/order-123",
        )

    assert invoice["uuid"] is None
    assert invoice["checkout_url"] == (
        "https://checkout.multicard.uz/?store_id="
        f"{settings.multicard_store_id}&invoice_id=order-123"
    )


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
    cancel_invoice = AsyncMock(side_effect=RuntimeError("already paid or unavailable"))

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=cancel_invoice,
    ):
        expired = await expire_due_payment_orders(
            db_session,
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )
        repeated = await expire_due_payment_orders(
            db_session,
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )

    await db_session.refresh(order)
    assert expired == 0
    assert repeated == 0
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    assert order.payment_status == "pending"
    assert order.status == "AWAITING_PAYMENT"
    assert order.invoice_cancel_status == "unknown"


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
    assert order.invoice_cancel_status == "cancelled"


@pytest.mark.asyncio
async def test_interrupted_invoice_cancel_is_recovered_as_unknown(db_session):
    user = await _customer(db_session)
    order = await _expired_online_order(db_session, user)
    order.invoice_cancel_status = "sending"
    await db_session.commit()

    recovered = await order_service.recover_interrupted_invoice_cancellations(
        db_session
    )

    await db_session.refresh(order)
    assert recovered == 1
    assert order.invoice_cancel_status == "unknown"
    assert order.payment_status == "pending"


@pytest.mark.asyncio
async def test_invoice_cancel_transport_failure_is_unknown_after_one_delete():
    client = Mock()
    client.delete = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.multicard_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.multicard_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(multicard_api.InvoiceCancelOutcomeUnknown):
            await multicard_api.cancel_invoice_strict("invoice-uuid")

    client.delete.assert_awaited_once()


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
async def test_alipos_create_order_does_not_follow_mutation_redirect():
    real_client = httpx.AsyncClient
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.url.host == "redirect-target.example":
            return httpx.Response(
                200,
                json={"orderId": str(uuid.uuid4())},
                request=request,
            )
        return httpx.Response(
            307,
            headers={"Location": "https://redirect-target.example/replayed-order"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "app.services.alipos_api.httpx.AsyncClient",
            side_effect=lambda *args, **kwargs: real_client(transport=transport),
        ),
    ):
        with pytest.raises(alipos_api.AliPOSUnknownOutcome):
            await alipos_api.create_order({"eatsId": "stable-id"})

    assert len(requests) == 1
    assert requests[0][0] == "POST"
    assert "redirect-target.example" not in requests[0][1]


@pytest.mark.asyncio
async def test_alipos_cancel_order_does_not_follow_mutation_redirect():
    real_client = httpx.AsyncClient
    requests: list[tuple[str, str]] = []
    provider_order_id = "11111111-1111-4111-8111-111111111111"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if request.url.host == "redirect-target.example":
            return httpx.Response(200, json={"result": "OK"}, request=request)
        return httpx.Response(
            308,
            headers={"Location": "https://redirect-target.example/replayed-cancel"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "app.services.alipos_api.httpx.AsyncClient",
            side_effect=lambda *args, **kwargs: real_client(transport=transport),
        ),
    ):
        with pytest.raises(RuntimeError, match="outcome is unknown"):
            await alipos_api.cancel_order(provider_order_id, "cancel once")

    assert len(requests) == 1
    assert requests[0][0] == "DELETE"
    assert "redirect-target.example" not in requests[0][1]


@pytest.mark.asyncio
async def test_alipos_cancel_runtime_failure_suppresses_unsafe_cause():
    provider_order_id = "cancel-path-canary-55555555"
    unsafe_detail = "https://provider-secret.example?token=credential-canary-66666666"
    client = Mock()
    client.__aenter__ = AsyncMock(side_effect=RuntimeError(unsafe_detail))
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await alipos_api.cancel_order(provider_order_id, "cancel once")

    assert exc_info.value.__cause__ is None
    assert provider_order_id not in str(exc_info.value)
    assert unsafe_detail not in str(exc_info.value)


@pytest.mark.asyncio
async def test_alipos_read_http_error_omits_path_body_and_exception_cause(caplog):
    provider_order_id = "order-path-canary-11111111"
    provider_body = "provider-body-canary-22222222"
    response = httpx.Response(
        500,
        json={"detail": provider_body},
        request=httpx.Request(
            "GET",
            f"https://alipos.example/api/Integration/v1/order/{provider_order_id}",
        ),
    )
    client = Mock()
    client.request = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        caplog.at_level("WARNING", logger="app.services.alipos_api"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await alipos_api.get_order_status(provider_order_id)

    assert exc_info.value.__cause__ is None
    assert provider_order_id not in str(exc_info.value)
    assert provider_body not in str(exc_info.value)
    assert provider_order_id not in caplog.text
    assert provider_body not in caplog.text
    assert "order_read" in caplog.text
    assert "500" in caplog.text


@pytest.mark.asyncio
async def test_alipos_read_transport_error_omits_url_and_exception_cause(caplog):
    provider_order_id = "order-path-canary-33333333"
    unsafe_url = (
        "https://alipos.example/api/Integration/v1/order/"
        f"{provider_order_id}?access_token=credential-canary-44444444"
    )
    client = Mock()
    client.request = AsyncMock(
        side_effect=httpx.ReadTimeout(
            f"transport failed for {unsafe_url}",
            request=httpx.Request("GET", unsafe_url),
        )
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.alipos_api._get_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.services.alipos_api.httpx.AsyncClient", return_value=client),
        patch("app.services.alipos_api.asyncio.sleep", new=AsyncMock()),
        caplog.at_level("WARNING", logger="app.services.alipos_api"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await alipos_api.get_order_status(provider_order_id)

    assert exc_info.value.__cause__ is None
    assert provider_order_id not in str(exc_info.value)
    assert unsafe_url not in str(exc_info.value)
    assert provider_order_id not in caplog.text
    assert unsafe_url not in caplog.text
    assert "credential-canary-44444444" not in caplog.text
    assert "order_read" in caplog.text


@pytest.mark.asyncio
async def test_alipos_read_invalid_json_omits_response_body_and_exception_cause():
    provider_order_id = "order-path-canary-77777777"
    provider_body = "provider-body-canary-88888888"
    response = httpx.Response(
        200,
        content=provider_body,
        request=httpx.Request(
            "GET",
            f"https://alipos.example/api/Integration/v1/order/{provider_order_id}",
        ),
    )

    with patch(
        "app.services.alipos_api._api_request",
        new=AsyncMock(return_value=response),
    ):
        with pytest.raises(RuntimeError, match="AliPOS order_read response invalid") as exc_info:
            await alipos_api.get_order_status(provider_order_id)

    assert exc_info.value.__cause__ is None
    assert provider_order_id not in str(exc_info.value)
    assert provider_body not in str(exc_info.value)


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
async def test_paid_rejection_queues_refund_in_failure_commit_before_dispatch(
    db_session,
):
    class SimulatedProcessExit(BaseException):
        pass

    class CrashAfterFailureCommit:
        def __init__(self, delegate: AsyncSession) -> None:
            self.delegate = delegate
            self.commit_count = 0

        def __getattr__(self, name: str):
            return getattr(self.delegate, name)

        async def commit(self) -> None:
            await self.delegate.commit()
            self.commit_count += 1
            if self.commit_count == 2:
                raise SimulatedProcessExit

    user = await _customer(db_session)
    order = await _queued_order(
        db_session,
        user,
        payment_method="rahmat",
        payment_status="paid",
    )
    order.multicard_payment_uuid = "payment-uuid"
    await db_session.commit()
    crashing_db = CrashAfterFailureCommit(db_session)
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
        with pytest.raises(SimulatedProcessExit):
            await submit_order_to_alipos(crashing_db, order)

    await db_session.refresh(order)
    refund.assert_not_awaited()
    assert order.alipos_sync_status == "failed"
    assert order.status == "SUBMISSION_FAILED"
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "queued"


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
