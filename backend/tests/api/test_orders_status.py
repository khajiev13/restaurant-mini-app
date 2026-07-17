import datetime
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.main import app
from app.middleware.telegram_auth import create_jwt
from app.models.models import Order, User
from app.services import order_service


@pytest_asyncio.fixture
async def cancellation_sessions(db_session):
    _ = db_session  # Ensure the test schema exists before opening new connections.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_user_ids: list[int] = []

    async def override_get_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as committing_client:
            yield committing_client, sessions, created_user_ids
    finally:
        app.dependency_overrides.pop(get_db, None)
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


async def _table_order(db_session, *, paid: bool = False) -> tuple[User, Order]:
    telegram_id = 9_000_000_000 + uuid.uuid4().int % 1_000_000_000
    user = User(
        telegram_id=telegram_id,
        first_name="Table customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=telegram_id,
        items=[],
        delivery_info={"clientName": "Table customer", "phoneNumber": "+998900000000"},
        items_cost=36000,
        total_amount=39600,
        delivery_fee=0,
        payment_method="rahmat" if paid else "cash",
        payment_provider="multicard" if paid else None,
        payment_status="paid" if paid else None,
        multicard_payment_uuid="payment-uuid" if paid else None,
        discriminator="inplace",
        table_id=uuid.uuid4(),
        alipos_order_id=uuid.uuid4(),
        alipos_eats_id=f"cancel-{uuid.uuid4().hex}",
        alipos_sync_status="synced",
        status="NEW",
    )
    db_session.add_all([user, order])
    await db_session.commit()
    return user, order


async def _pending_online_table_order(db_session) -> tuple[User, Order]:
    telegram_id = 9_000_000_000 + uuid.uuid4().int % 1_000_000_000
    user = User(
        telegram_id=telegram_id,
        first_name="Table customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=telegram_id,
        items=[],
        delivery_info={"clientName": "Table customer", "phoneNumber": "+998900000000"},
        items_cost=36000,
        total_amount=39600,
        delivery_fee=0,
        payment_method="rahmat",
        payment_provider="multicard",
        payment_status="pending",
        payment_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        + datetime.timedelta(minutes=10),
        multicard_invoice_uuid="invoice-uuid",
        multicard_checkout_url="https://pay.example/checkout",
        discriminator="inplace",
        table_id=uuid.uuid4(),
        alipos_eats_id=f"switch-{uuid.uuid4().hex}",
        alipos_sync_status="awaiting_payment",
        status="AWAITING_PAYMENT",
    )
    db_session.add_all([user, order])
    await db_session.commit()
    return user, order


async def _failed_online_table_order(db_session) -> tuple[User, Order]:
    user, order = await _pending_online_table_order(db_session)
    order.payment_status = "failed"
    order.payment_error = "Could not create the online payment"
    order.payment_expires_at = None
    order.multicard_invoice_uuid = None
    order.multicard_checkout_url = None
    order.status = "PAYMENT_FAILED"
    await db_session.commit()
    return user, order


@pytest.mark.asyncio
async def test_order_status_poll_does_not_overwrite_local_delivered(client, db_session):
    user = User(
        telegram_id=6101,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=6101,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_order_id=uuid.uuid4(),
        status="DELIVERED",
        delivered_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
    db_session.add_all([user, order])
    await db_session.commit()

    token = create_jwt(user.telegram_id)
    with patch(
        "app.routers.orders.alipos_api.get_order_status",
        new=AsyncMock(return_value={"status": "TAKEN_BY_COURIER", "orderNumber": "99"}),
    ):
        response = await client.get(
            f"/api/orders/{order.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "DELIVERED"
    assert order.status == "DELIVERED"
    assert order.order_number is None


@pytest.mark.asyncio
async def test_order_status_poll_does_not_overwrite_delivery_that_wins_race(
    client,
    db_session,
):
    user = User(
        telegram_id=6102,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=6102,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_order_id=uuid.uuid4(),
        status="TAKEN_BY_COURIER",
    )
    db_session.add_all([user, order])
    await db_session.commit()

    async def deliver_before_alipos_returns(_alipos_order_id: str):
        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        await db_session.execute(
            text(
                "UPDATE orders "
                "SET status = 'DELIVERED', delivered_at = :now, status_updated_at = :now "
                "WHERE id = :order_id"
            ),
            {"now": now, "order_id": order.id},
        )
        await db_session.flush()
        return {"status": "READY", "orderNumber": "99"}

    token = create_jwt(user.telegram_id)
    with patch(
        "app.routers.orders.alipos_api.get_order_status",
        new=AsyncMock(side_effect=deliver_before_alipos_returns),
    ):
        response = await client.get(
            f"/api/orders/{order.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "DELIVERED"
    assert order.status == "DELIVERED"
    assert order.order_number is None


@pytest.mark.asyncio
async def test_new_cash_table_order_can_be_cancelled(client, db_session):
    user, order = await _table_order(db_session)
    cancel = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel.assert_awaited_once_with(
        str(order.alipos_order_id),
        "Mijoz yangi buyurtmani bekor qildi",
    )
    assert order.status == "CANCELLED"
    assert response.json()["data"]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_accepted_table_order_cannot_be_cancelled(client, db_session):
    user, order = await _table_order(db_session)
    cancel = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "ACCEPTED_BY_RESTAURANT"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 409
    cancel.assert_not_awaited()
    assert order.status == "ACCEPTED_BY_RESTAURANT"


@pytest.mark.asyncio
async def test_paid_table_order_refunds_after_alipos_cancel(client, db_session):
    user, order = await _table_order(db_session, paid=True)
    refund = AsyncMock(return_value={"success": True})
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    refund.assert_awaited_once_with("payment-uuid")
    assert order.status == "CANCELLED"
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"
    assert response.json()["data"]["payment_status"] == "refunded"


@pytest.mark.asyncio
async def test_paid_table_order_keeps_refund_pending_when_outcome_is_unknown(
    client,
    db_session,
):
    user, order = await _table_order(db_session, paid=True)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=AsyncMock(side_effect=httpx.ReadTimeout("outcome unknown")),
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "CANCELLED"
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "unknown"
    assert response.json()["data"]["payment_status"] == "refund_pending"


@pytest.mark.asyncio
async def test_alipos_cancel_attempt_is_durable_before_delete(cancellation_sessions):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        alipos_order_id = order.alipos_order_id

    observed: dict[str, object] = {}

    async def observe_durable_attempt(provider_order_id: str, comment: str) -> None:
        observed["provider_order_id"] = provider_order_id
        observed["comment"] = comment
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            observed["status"] = persisted.alipos_cancel_status
            observed["requested_at"] = persisted.cancel_requested_at

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(side_effect=observe_durable_attempt),
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    assert observed["provider_order_id"] == str(alipos_order_id)
    assert str(observed["comment"]).strip()
    assert observed["status"] == "sending"
    assert observed["requested_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
async def test_local_cancel_that_wins_before_claim_stays_cancelled(
    cancellation_sessions,
    local_status,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id

    async def cancel_locally_before_claim(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order).where(Order.id == order_id).values(status=local_status)
            )
            await race_db.commit()
        return {"status": "NEW"}

    cancel = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=cancel_locally_before_claim),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    cancel.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
async def test_paid_synced_local_cancel_finalizes_refund_without_alipos_calls(
    cancellation_sessions,
    local_status,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        order.status = local_status
        order.alipos_cancel_status = None
        await seed_db.commit()

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    get_status = AsyncMock()
    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    get_status.assert_not_awaited()
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": local_status,
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_provider_cancelled_preclaim_finalizes_concurrent_sending_attempt(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id

    async def concurrent_attempt_reaches_provider(
        _provider_order_id: str,
    ) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(
                    alipos_cancel_status="sending",
                    cancel_requested_at=datetime.datetime.now(datetime.UTC).replace(
                        tzinfo=None
                    ),
                )
            )
            await race_db.commit()
        return {"status": "CANCELLED"}

    cancel = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=concurrent_attempt_reaches_provider),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    cancel.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"


@pytest.mark.asyncio
async def test_preclaim_later_status_preserves_concurrent_cancelled_result(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id

    async def concurrent_cancel_wins(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="CANCELLED", alipos_cancel_status="cancelled")
            )
            await race_db.commit()
        return {"status": "ACCEPTED_BY_RESTAURANT"}

    cancel = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=concurrent_cancel_wins),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    cancel.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"


@pytest.mark.asyncio
async def test_provider_later_status_finalizes_concurrent_local_cancel_and_refund(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        provider_order_id = str(order.alipos_order_id)
        order.alipos_cancel_status = "not_started"
        await seed_db.commit()

    async def local_cancel_wins(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order).where(Order.id == order_id).values(status="CANCELLED")
            )
            await race_db.commit()
        return {"status": "ACCEPTED_BY_RESTAURANT"}

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    get_status = AsyncMock(side_effect=local_cancel_wins)
    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 200
    get_status.assert_awaited_once_with(provider_order_id)
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": "CANCELLED",
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_unknown_alipos_cancel_retry_never_sends_second_delete(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id

    get_status = AsyncMock(return_value={"status": "NEW"})
    cancel = AsyncMock(side_effect=httpx.ReadTimeout("outcome unknown"))
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        first = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )
        second = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert first.status_code == 502
    assert second.status_code == 502
    assert get_status.await_count == 2
    cancel.assert_awaited_once()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.alipos_cancel_status == "unknown"


@pytest.mark.asyncio
async def test_unknown_paid_cancel_reconciles_cancelled_and_queues_one_refund(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        order.alipos_cancel_status = "unknown"
        order.alipos_cancel_error = "AliPOS cancellation outcome is unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "CANCELLED"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )

    assert reconciled == 1
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": "CANCELLED",
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_delivered_paid_order_never_auto_refunds_on_cancel_reconciliation(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        delivered_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)
        order.status = "DELIVERED"
        order.delivered_at = delivered_at
        order.status_updated_at = delivered_at
        order.alipos_cancel_status = "unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    refund = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "CANCELLED"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ) as cancel,
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )

    assert reconciled == 1
    cancel.assert_not_awaited()
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "DELIVERED"
        assert persisted.status_updated_at == delivered_at
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
async def test_not_cancelled_reconciliation_preserves_concurrent_ready_status(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        ready_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)
        order.alipos_cancel_status = "unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    async def ready_wins_before_get_returns(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="READY", status_updated_at=ready_at)
            )
            await race_db.commit()
        return {"status": "ACCEPTED_BY_RESTAURANT"}

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=ready_wins_before_get_returns),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ) as cancel,
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )

    assert reconciled == 1
    cancel.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "READY"
        assert persisted.status_updated_at == ready_at
        assert persisted.alipos_cancel_status == "not_cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
async def test_unknown_reconciliation_finalizes_concurrent_local_cancel_and_refund(
    cancellation_sessions,
    local_status,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        provider_order_id = str(order.alipos_order_id)
        order.alipos_cancel_status = "unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    async def local_cancel_wins(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order).where(Order.id == order_id).values(status=local_status)
            )
            await race_db.commit()
        return {"status": "ACCEPTED_BY_RESTAURANT"}

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=local_cancel_wins),
        ) as get_status,
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ) as cancel,
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=5,
            )

    assert reconciled == 1
    get_status.assert_awaited_once_with(provider_order_id)
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": local_status,
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel_marker", "local_status", "get_outcome"),
    [
        ("unknown", "CANCELLED", "error"),
        ("sending", "CANCELED", "new"),
    ],
)
async def test_reconciliation_fallback_finalizes_concurrent_local_cancel(
    cancellation_sessions,
    cancel_marker,
    local_status,
    get_outcome,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        provider_order_id = str(order.alipos_order_id)
        order.alipos_cancel_status = cancel_marker
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    async def local_cancel_wins(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order).where(Order.id == order_id).values(status=local_status)
            )
            await race_db.commit()
        if get_outcome == "error":
            raise httpx.ReadTimeout("status outcome unknown")
        return {"status": "NEW"}

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    get_status = AsyncMock(side_effect=local_cancel_wins)
    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=5,
            )
        async with sessions() as second_reconcile_db:
            reconciled_again = (
                await order_service.reconcile_unknown_alipos_cancellations(
                    second_reconcile_db,
                    limit=5,
                )
            )

    assert reconciled == 1
    assert reconciled_again == 0
    get_status.assert_awaited_once_with(provider_order_id)
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": local_status,
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
@pytest.mark.parametrize("webhook_status", ["CANCELLED", "CANCELED"])
@pytest.mark.parametrize("repair_path", ["customer", "reconciler"])
async def test_authenticated_local_cancel_supersedes_not_cancelled_marker(
    cancellation_sessions,
    monkeypatch,
    webhook_status,
    repair_path,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        eats_id = order.alipos_eats_id
        order.alipos_cancel_status = "not_cancelled"
        await seed_db.commit()

    monkeypatch.setattr(settings, "alipos_api_client_id", "test-client")
    monkeypatch.setattr(settings, "alipos_api_client_secret", "test-secret")
    with patch("app.routers.webhooks.async_session", new=sessions):
        webhook_response = await committing_client.post(
            "/api/webhooks/order-status",
            json={"eatsId": eats_id, "status": webhook_status},
            headers={"clientId": "test-client", "clientSecret": "test-secret"},
        )
    assert webhook_response.status_code == 200

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    get_status = AsyncMock()
    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        if repair_path == "customer":
            response = await committing_client.delete(
                f"/api/orders/{order_id}",
                headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
            )
            assert response.status_code == 200
        else:
            async with sessions() as reconcile_db:
                reconciled = (
                    await order_service.reconcile_unknown_alipos_cancellations(
                        reconcile_db,
                        limit=5,
                    )
                )
            assert reconciled == 1
        async with sessions() as second_reconcile_db:
            reconciled_again = (
                await order_service.reconcile_unknown_alipos_cancellations(
                    second_reconcile_db,
                    limit=5,
                )
            )

    assert reconciled_again == 0
    get_status.assert_not_awaited()
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": "CANCELLED",
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_bounded_reconciliation_repairs_local_cancel_markers_only(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    repair_markers = [None, "not_started", "not_cancelled", "sending", "unknown"]
    repair_orders: dict[str, tuple[uuid.UUID, str]] = {}
    ancient = datetime.datetime(2000, 1, 1)

    async with sessions() as seed_db:
        for index, marker in enumerate(repair_markers):
            user, order = await _table_order(seed_db, paid=True)
            created_user_ids.append(user.telegram_id)
            local_status = "CANCELLED" if index % 2 == 0 else "CANCELED"
            payment_uuid = f"repair-payment-{index}"
            order.status = local_status
            order.alipos_cancel_status = marker
            order.cancel_requested_at = ancient + datetime.timedelta(seconds=index)
            order.multicard_payment_uuid = payment_uuid
            repair_orders[payment_uuid] = (order.id, local_status)

        finalized_user, finalized_order = await _table_order(seed_db, paid=True)
        created_user_ids.append(finalized_user.telegram_id)
        finalized_order.status = "CANCELLED"
        finalized_order.alipos_cancel_status = "cancelled"
        finalized_order.payment_status = "refunded"
        finalized_order.refund_sync_status = "refunded"
        finalized_order.multicard_payment_uuid = "already-finalized-payment"
        finalized_order_id = finalized_order.id
        await seed_db.commit()

    refund_observed: set[str] = set()

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        order_id, local_status = repair_orders[payment_uuid]
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            assert persisted.status == local_status
            assert persisted.alipos_cancel_status == "cancelled"
            assert persisted.payment_status == "refund_pending"
            assert persisted.refund_sync_status == "sending"
        refund_observed.add(payment_uuid)
        return {"success": True}

    get_status = AsyncMock(return_value={"status": "NEW"})
    cancel = AsyncMock()
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=5,
            )
        async with sessions() as second_reconcile_db:
            reconciled_again = (
                await order_service.reconcile_unknown_alipos_cancellations(
                    second_reconcile_db,
                    limit=5,
                )
            )

    assert reconciled == 5
    assert reconciled_again == 0
    get_status.assert_not_awaited()
    cancel.assert_not_awaited()
    assert refund.await_count == 5
    assert refund_observed == set(repair_orders)
    async with sessions() as observer_db:
        for payment_uuid, (order_id, local_status) in repair_orders.items():
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            assert persisted.status == local_status
            assert persisted.alipos_cancel_status == "cancelled"
            assert persisted.payment_status == "refunded"
            assert persisted.refund_sync_status == "refunded"
            assert persisted.multicard_payment_uuid == payment_uuid

        finalized = await observer_db.get(Order, finalized_order_id)
        assert finalized is not None
        assert finalized.status == "CANCELLED"
        assert finalized.alipos_cancel_status == "cancelled"
        assert finalized.payment_status == "refunded"
        assert finalized.refund_sync_status == "refunded"
        assert finalized.multicard_payment_uuid == "already-finalized-payment"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
@pytest.mark.parametrize(
    "race_point",
    [
        "preflight_error",
        "preflight_empty",
        "provider_cancelled_noop",
        "delete_error",
        "delete_success_noop",
    ],
)
async def test_request_finalizes_local_cancel_that_wins_provider_boundary(
    cancellation_sessions,
    local_status,
    race_point,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        provider_order_id = str(order.alipos_order_id)

    async def commit_local_cancel(*, stale_marker: bool = False) -> None:
        values: dict[str, str] = {"status": local_status}
        if stale_marker:
            values["alipos_cancel_status"] = "not_cancelled"
        async with sessions() as race_db:
            await race_db.execute(
                update(Order).where(Order.id == order_id).values(**values)
            )
            await race_db.commit()

    async def preflight_side_effect(_provider_order_id: str) -> dict[str, str]:
        if race_point == "preflight_error":
            await commit_local_cancel()
            raise httpx.ReadTimeout("provider status outcome unknown")
        if race_point == "preflight_empty":
            await commit_local_cancel()
            return {}
        if race_point == "provider_cancelled_noop":
            await commit_local_cancel(stale_marker=True)
            return {"status": "CANCELLED"}
        return {"status": "NEW"}

    async def delete_side_effect(
        _provider_order_id: str,
        _comment: str,
    ) -> None:
        if race_point == "delete_error":
            await commit_local_cancel()
            raise httpx.ReadTimeout("provider cancellation outcome unknown")
        if race_point == "delete_success_noop":
            await commit_local_cancel(stale_marker=True)

    refund_observed: dict[str, object] = {}

    async def observe_queued_refund(payment_uuid: str) -> dict[str, bool]:
        refund_observed["payment_uuid"] = payment_uuid
        async with sessions() as observer_db:
            persisted = await observer_db.get(Order, order_id)
            assert persisted is not None
            refund_observed["order_status"] = persisted.status
            refund_observed["cancel_status"] = persisted.alipos_cancel_status
            refund_observed["payment_status"] = persisted.payment_status
            refund_observed["refund_status"] = persisted.refund_sync_status
        return {"success": True}

    get_status = AsyncMock(side_effect=preflight_side_effect)
    cancel = AsyncMock(side_effect=delete_side_effect)
    refund = AsyncMock(side_effect=observe_queued_refund)
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        first = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )
        second = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    get_status.assert_awaited_once_with(provider_order_id)
    expected_delete_count = int(race_point in {"delete_error", "delete_success_noop"})
    assert cancel.await_count == expected_delete_count
    refund.assert_awaited_once_with("payment-uuid")
    assert refund_observed == {
        "payment_uuid": "payment-uuid",
        "order_status": local_status,
        "cancel_status": "cancelled",
        "payment_status": "refund_pending",
        "refund_status": "sending",
    }
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_local_cancel_repair_helper_does_not_cancel_new_order(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        order.alipos_cancel_status = "not_started"
        await seed_db.commit()

    refund = AsyncMock()
    with patch(
        "app.services.order_service.multicard_api.refund_payment",
        new=refund,
    ):
        async with sessions() as repair_db:
            repaired, finalized = (
                await order_service._finalize_current_local_alipos_cancel(
                    repair_db,
                    order_id,
                )
            )

    assert repaired is not None
    assert finalized is False
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "NEW"
        assert persisted.alipos_cancel_status == "not_started"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
async def test_mark_unknown_repairs_cancel_committed_before_reload(
    cancellation_sessions,
    local_status,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        order.alipos_cancel_status = "sending"
        await seed_db.commit()

    original_reload = order_service._reload_order
    reload_count = 0

    async def cancel_before_first_reload(db, reloaded_order_id):
        nonlocal reload_count
        reload_count += 1
        if reload_count == 1:
            async with sessions() as race_db:
                await race_db.execute(
                    update(Order)
                    .where(Order.id == order_id)
                    .values(status=local_status)
                )
                await race_db.commit()
        return await original_reload(db, reloaded_order_id)

    refund = AsyncMock(return_value={"success": True})
    with (
        patch(
            "app.services.order_service._reload_order",
            new=AsyncMock(side_effect=cancel_before_first_reload),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as repair_db:
            repaired, finalized = (
                await order_service._mark_cancel_unknown_or_finalize_local_cancel(
                    repair_db,
                    order_id,
                )
            )

    assert repaired is not None
    assert finalized is True
    refund.assert_awaited_once_with("payment-uuid")
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["CANCELLED", "CANCELED"])
async def test_provider_cancelled_reconciliation_repairs_stale_not_cancelled(
    cancellation_sessions,
    local_status,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        provider_order_id = str(order.alipos_order_id)
        order.alipos_cancel_status = "unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    async def stale_marker_wins(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(
                    status=local_status,
                    alipos_cancel_status="not_cancelled",
                )
            )
            await race_db.commit()
        return {"status": "CANCELLED"}

    get_status = AsyncMock(side_effect=stale_marker_wins)
    cancel = AsyncMock()
    refund = AsyncMock(return_value={"success": True})
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=5,
            )
        async with sessions() as second_reconcile_db:
            reconciled_again = (
                await order_service.reconcile_unknown_alipos_cancellations(
                    second_reconcile_db,
                    limit=5,
                )
            )

    assert reconciled == 1
    assert reconciled_again == 0
    get_status.assert_awaited_once_with(provider_order_id)
    cancel.assert_not_awaited()
    refund.assert_awaited_once_with("payment-uuid")
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == local_status
        assert persisted.alipos_cancel_status == "cancelled"
        assert persisted.payment_status == "refunded"
        assert persisted.refund_sync_status == "refunded"


@pytest.mark.asyncio
async def test_cancelled_reconciliation_preserves_concurrent_ready_without_refund(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        ready_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)
        order.alipos_cancel_status = "unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    async def ready_wins_before_get_returns(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="READY", status_updated_at=ready_at)
            )
            await race_db.commit()
        return {"status": "CANCELLED"}

    refund = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=ready_wins_before_get_returns),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ) as cancel,
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=5,
            )

    assert reconciled == 1
    cancel.assert_not_awaited()
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "READY"
        assert persisted.status_updated_at == ready_at
        assert persisted.alipos_cancel_status == "not_cancelled"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
async def test_first_cancel_preserves_ready_that_wins_before_cancelled_get_returns(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        ready_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)

    async def ready_wins_before_get_returns(_provider_order_id: str) -> dict[str, str]:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="READY", status_updated_at=ready_at)
            )
            await race_db.commit()
        return {"status": "CANCELLED"}

    cancel = AsyncMock()
    refund = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=ready_wins_before_get_returns),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 409
    cancel.assert_not_awaited()
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "READY"
        assert persisted.status_updated_at == ready_at
        assert persisted.alipos_cancel_status == "not_cancelled"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
async def test_cancel_delete_success_preserves_ready_that_wins_before_finalize(
    cancellation_sessions,
):
    committing_client, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        user_id = user.telegram_id
        order_id = order.id
        ready_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(seconds=5)

    async def ready_wins_before_finalize(
        _provider_order_id: str,
        _comment: str,
    ) -> None:
        async with sessions() as race_db:
            await race_db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="READY", status_updated_at=ready_at)
            )
            await race_db.commit()

    cancel = AsyncMock(side_effect=ready_wins_before_finalize)
    refund = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await committing_client.delete(
            f"/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {create_jwt(user_id)}"},
        )

    assert response.status_code == 409
    cancel.assert_awaited_once()
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "READY"
        assert persisted.status_updated_at == ready_at
        assert persisted.alipos_cancel_status == "not_cancelled"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
async def test_cancel_reconciliation_clamps_requested_batch_size(cancellation_sessions):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        for _ in range(6):
            user, order = await _table_order(seed_db)
            created_user_ids.append(user.telegram_id)
            order.alipos_cancel_status = "unknown"
            order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
                tzinfo=None
            )
        await seed_db.commit()

    get_status = AsyncMock(return_value={"status": "NEW"})
    with patch(
        "app.services.order_service.alipos_api.get_order_status",
        new=get_status,
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=999,
            )

    assert reconciled == 0
    assert get_status.await_count == 5


@pytest.mark.asyncio
async def test_interrupted_cancel_recovery_uses_get_without_delete(
    cancellation_sessions,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        order.alipos_cancel_status = "sending"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    get_status = AsyncMock(return_value={"status": "CANCELLED"})
    cancel = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        async with sessions() as reconcile_db:
            reconciled = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )

    assert reconciled == 1
    get_status.assert_awaited_once()
    cancel.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "CANCELLED"
        assert persisted.alipos_cancel_status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", ["ACCEPTED_BY_RESTAURANT", "READY"])
async def test_unknown_cancel_reconciles_later_status_to_not_cancelled_without_refund(
    cancellation_sessions,
    provider_status,
):
    _, sessions, created_user_ids = cancellation_sessions
    async with sessions() as seed_db:
        user, order = await _table_order(seed_db, paid=True)
        created_user_ids.append(user.telegram_id)
        order_id = order.id
        order.alipos_cancel_status = "unknown"
        order.alipos_cancel_error = "AliPOS cancellation outcome is unknown"
        order.cancel_requested_at = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        )
        await seed_db.commit()

    get_status = AsyncMock(return_value={"status": provider_status})
    cancel = AsyncMock()
    refund = AsyncMock()
    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=get_status,
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        async with sessions() as reconcile_db:
            first = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )
            second = await order_service.reconcile_unknown_alipos_cancellations(
                reconcile_db,
                limit=10,
            )

    assert first == 1
    assert second == 0
    get_status.assert_awaited_once()
    cancel.assert_not_awaited()
    refund.assert_not_awaited()
    async with sessions() as observer_db:
        persisted = await observer_db.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == provider_status
        assert persisted.alipos_cancel_status == "not_cancelled"
        assert persisted.payment_status == "paid"
        assert persisted.refund_sync_status is None


@pytest.mark.asyncio
async def test_pending_online_table_order_can_switch_to_cash(client, db_session):
    user, order = await _pending_online_table_order(db_session)
    cancel_invoice = AsyncMock()
    submit = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=cancel_invoice,
        ),
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=submit,
        ),
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    submit.assert_awaited_once()
    assert order.payment_method == "cash"
    assert order.payment_provider is None
    assert order.payment_status is None
    assert order.multicard_checkout_url is None
    assert order.status == "NEW"
    assert order.alipos_sync_status == "sending"


@pytest.mark.asyncio
async def test_pending_online_table_order_cancels_invoice_before_local_order(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    cancel_invoice = AsyncMock()
    token = create_jwt(user.telegram_id)

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=cancel_invoice,
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    assert order.status == "CANCELLED"
    assert order.payment_status == "cancelled"


@pytest.mark.asyncio
async def test_pending_online_order_stays_payable_when_invoice_cancel_is_unknown(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=AsyncMock(side_effect=RuntimeError("Multicard unavailable")),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 502
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_status == "pending"


@pytest.mark.asyncio
async def test_switch_to_cash_keeps_online_order_when_invoice_cancel_is_unknown(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=AsyncMock(side_effect=RuntimeError("Multicard unavailable")),
        ),
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=AsyncMock(),
        ) as submit,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 502
    submit.assert_not_awaited()
    assert order.payment_method == "rahmat"
    assert order.payment_status == "pending"
    assert order.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_failed_online_payment_can_create_a_fresh_checkout(
    client,
    db_session,
    monkeypatch,
):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", True)
    invoice = AsyncMock(return_value={
        "uuid": "new-invoice-uuid",
        "checkout_url": "https://pay.example/new-checkout",
    })

    with patch(
        "app.services.order_service.multicard_api.create_invoice",
        new=invoice,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/retry-payment",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_status == "pending"
    assert order.multicard_invoice_uuid == "new-invoice-uuid"
    assert response.json()["data"]["multicard_checkout_url"] == (
        "https://pay.example/new-checkout"
    )


@pytest.mark.asyncio
async def test_failed_online_payment_retry_is_blocked_after_capability_disabled(
    client,
    db_session,
    monkeypatch,
):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "")
    invoice = AsyncMock(
        return_value={
            "uuid": "unexpected-invoice-uuid",
            "checkout_url": "https://pay.example/unexpected-checkout",
        }
    )

    with patch(
        "app.services.order_service.multicard_api.create_invoice",
        new=invoice,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/retry-payment",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Online payment is not available for table orders"
    )
    invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_online_payment_can_safely_switch_to_cash(client, db_session):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=AsyncMock(),
        ) as cancel_invoice,
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=AsyncMock(),
        ),
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_not_awaited()
    assert order.payment_method == "cash"
    assert order.payment_status is None
