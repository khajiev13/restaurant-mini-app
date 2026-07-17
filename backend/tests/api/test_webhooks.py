import asyncio
import datetime
import hashlib
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import register_telegram_webhook
from app.models.models import Order, User
from app.routers import webhooks as webhooks_router
from app.services import alipos_api, order_service


@pytest.fixture
def webhook_db_session(db_session, monkeypatch):
    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(webhooks_router, "async_session", _session_override)
    return db_session


@pytest_asyncio.fixture
async def webhook_race_sessions(db_session, monkeypatch):
    _ = db_session  # Ensure the test schema exists before opening new connections.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_user_ids: list[int] = []
    webhook_session_ids: list[int] = []

    @asynccontextmanager
    async def webhook_session():
        async with sessions() as session:
            webhook_session_ids.append(id(session))
            yield session

    monkeypatch.setattr(webhooks_router, "async_session", webhook_session)
    try:
        yield sessions, created_user_ids, webhook_session_ids
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


@pytest.mark.asyncio
async def test_telegram_bot_webhook_updates_phone_number(
    client,
    webhook_db_session,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")
    user = User(
        telegram_id=12345678,
        first_name="Test",
        last_name=None,
        username="tester",
    )
    webhook_db_session.add(user)
    await webhook_db_session.commit()

    payload = {
        "update_id": 101,
        "message": {
            "from": {"id": 12345678},
            "contact": {"user_id": 12345678, "phone_number": "+998901234567"},
        },
    }

    with caplog.at_level("INFO", logger="app.routers.webhooks"):
        response = await client.post(
            "/api/webhooks/bot",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": "test-secret"},
        )

    await webhook_db_session.refresh(user)

    assert response.status_code == 200
    assert user.phone_number == "+998901234567"
    assert "result=phone_saved" in caplog.text
    assert "+998901234567" not in caplog.text


@pytest.mark.asyncio
async def test_telegram_bot_webhook_ignores_messages_without_contact(
    client, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")

    with caplog.at_level("INFO", logger="app.routers.webhooks"):
        response = await client.post(
            "/api/webhooks/bot",
            json={"update_id": 102, "message": {"text": "hello"}},
            headers={"x-telegram-bot-api-secret-token": "test-secret"},
        )

    assert response.status_code == 200
    assert "result=no_contact" in caplog.text


@pytest.mark.asyncio
async def test_telegram_bot_webhook_rejects_invalid_secret(client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "expected-secret")

    with caplog.at_level("INFO", logger="app.routers.webhooks"):
        response = await client.post(
            "/api/webhooks/bot",
            json={"update_id": 103, "message": {}},
            headers={"x-telegram-bot-api-secret-token": "wrong-secret"},
        )

    assert response.status_code == 401
    assert "secret_valid=false" in caplog.text


@pytest.mark.asyncio
async def test_telegram_bot_webhook_ignores_unknown_user(
    client, webhook_db_session, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")

    payload = {
        "update_id": 104,
        "message": {
            "from": {"id": 87654321},
            "contact": {"user_id": 87654321, "phone_number": "+998998887766"},
        },
    }

    with caplog.at_level("INFO", logger="app.routers.webhooks"):
        response = await client.post(
            "/api/webhooks/bot",
            json=payload,
            headers={"x-telegram-bot-api-secret-token": "test-secret"},
        )

    assert response.status_code == 200
    assert "result=user_not_found" in caplog.text
    assert "+998998887766" not in caplog.text


@pytest.mark.asyncio
async def test_order_status_webhook_does_not_overwrite_local_delivered(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "alipos_api_client_id", "client")
    monkeypatch.setattr(settings, "alipos_api_client_secret", "secret")
    unique_suffix = int(datetime.datetime.now(datetime.UTC).timestamp() * 1_000_000)
    telegram_id = unique_suffix
    eats_id = f"eats-delivered-{unique_suffix}"

    user = User(
        telegram_id=telegram_id, first_name="Customer", last_name=None, username=None
    )
    order = Order(
        user_id=telegram_id,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_eats_id=eats_id,
        status="DELIVERED",
        delivered_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
    webhook_db_session.add_all([user, order])
    await webhook_db_session.commit()

    response = await client.post(
        "/api/webhooks/order-status",
        json={"eatsId": eats_id, "status": "TAKEN_BY_COURIER", "orderNumber": "99"},
        headers={"clientId": "client", "clientSecret": "secret"},
    )

    await webhook_db_session.refresh(order)

    assert response.status_code == 200
    assert order.status == "DELIVERED"
    assert order.order_number is None


async def _pending_online_order(db_session) -> Order:
    suffix = uuid.uuid4().int % 1_000_000_000
    user = User(
        telegram_id=8_000_000_000 + suffix,
        first_name="Table customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=user.telegram_id,
        items=[
            {
                "id": str(uuid.uuid4()),
                "name": "Classic Somsa",
                "quantity": 2,
                "price": 18000,
                "modifications": [],
            }
        ],
        delivery_info={"clientName": "Table customer", "phoneNumber": "+998900000000"},
        items_cost=36000,
        total_amount=39600,
        delivery_fee=0,
        payment_method="rahmat",
        payment_provider="multicard",
        payment_status="pending",
        discriminator="inplace",
        table_id=uuid.uuid4(),
        alipos_eats_id=f"callback-{uuid.uuid4().hex}",
        alipos_sync_status="awaiting_payment",
        status="AWAITING_PAYMENT",
    )
    db_session.add_all([user, order])
    await db_session.commit()
    return order


async def _paid_alipos_order(db_session) -> Order:
    order = await _pending_online_order(db_session)
    order.payment_status = "paid"
    order.multicard_payment_uuid = "payment-uuid"
    order.alipos_sync_status = "queued"
    order.status = "PAID_AWAITING_RESTAURANT"
    await db_session.commit()
    return order


def _mock_alipos_client(request: AsyncMock) -> Mock:
    client = Mock()
    client.request = request
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.mark.asyncio
async def test_paid_submit_success_preserves_status_webhook_that_wins_race(
    client,
    webhook_race_sessions,
    monkeypatch,
):
    monkeypatch.setattr(settings, "alipos_api_client_id", "client")
    monkeypatch.setattr(settings, "alipos_api_client_secret", "secret")
    sessions, created_user_ids, webhook_session_ids = webhook_race_sessions

    async with sessions() as submission_db:
        order = await _paid_alipos_order(submission_db)
        created_user_ids.append(order.user_id)
        provider_order_id = uuid.uuid4()
        request_started = asyncio.Event()
        release_request = asyncio.Event()

        async def blocked_request(*_args, **_kwargs):
            request_started.set()
            await release_request.wait()
            return httpx.Response(
                200,
                json={"result": "OK", "orderId": str(provider_order_id)},
                request=httpx.Request("POST", "https://alipos.example/order"),
            )

        request = AsyncMock(side_effect=blocked_request)
        monkeypatch.setattr(
            alipos_api,
            "get_payment_methods",
            AsyncMock(
                return_value=[{"id": str(uuid.uuid4()), "title": "online-order"}]
            ),
        )
        monkeypatch.setattr(alipos_api, "_get_token", AsyncMock(return_value="token"))
        monkeypatch.setattr(
            alipos_api.httpx,
            "AsyncClient",
            Mock(return_value=_mock_alipos_client(request)),
        )

        submit = asyncio.create_task(
            order_service.submit_order_to_alipos(submission_db, order)
        )
        try:
            await asyncio.wait_for(request_started.wait(), timeout=1)
            assert order.alipos_sync_status == "sending"

            response = await client.post(
                "/api/webhooks/order-status",
                json={
                    "eatsId": order.alipos_eats_id,
                    "status": "ACCEPTED_BY_RESTAURANT",
                    "orderNumber": "A-42",
                },
                headers={"clientId": "client", "clientSecret": "secret"},
            )
            assert response.status_code == 200
            assert webhook_session_ids[-1] != id(submission_db)
            async with sessions() as observer_db:
                persisted = await observer_db.get(Order, order.id)
                assert persisted is not None
                assert persisted.status == "ACCEPTED_BY_RESTAURANT"
                assert persisted.order_number == "A-42"
            assert order.status == "PAID_AWAITING_RESTAURANT"
            assert order.order_number is None

            release_request.set()
            await submit

            request.assert_awaited_once()
            assert order.alipos_sync_status == "synced"
            assert order.alipos_order_id == provider_order_id
            assert order.status == "ACCEPTED_BY_RESTAURANT"
            assert order.order_number == "A-42"
        finally:
            release_request.set()
            if not submit.done():
                await asyncio.gather(submit, return_exceptions=True)


@pytest.mark.asyncio
async def test_paid_submit_unknown_preserves_status_webhook_that_wins_race(
    client,
    webhook_race_sessions,
    monkeypatch,
):
    monkeypatch.setattr(settings, "alipos_api_client_id", "client")
    monkeypatch.setattr(settings, "alipos_api_client_secret", "secret")
    sessions, created_user_ids, webhook_session_ids = webhook_race_sessions

    async with sessions() as submission_db:
        order = await _paid_alipos_order(submission_db)
        created_user_ids.append(order.user_id)
        request_started = asyncio.Event()
        release_request = asyncio.Event()

        async def blocked_request(*_args, **_kwargs):
            request_started.set()
            await release_request.wait()
            return httpx.Response(
                502,
                json={"detail": "provider-secret"},
                request=httpx.Request("POST", "https://alipos.example/order"),
            )

        request = AsyncMock(side_effect=blocked_request)
        refund = AsyncMock()
        monkeypatch.setattr(
            alipos_api,
            "get_payment_methods",
            AsyncMock(
                return_value=[{"id": str(uuid.uuid4()), "title": "online-order"}]
            ),
        )
        monkeypatch.setattr(alipos_api, "_get_token", AsyncMock(return_value="token"))
        monkeypatch.setattr(
            alipos_api.httpx,
            "AsyncClient",
            Mock(return_value=_mock_alipos_client(request)),
        )
        monkeypatch.setattr(order_service.multicard_api, "refund_payment", refund)

        submit = asyncio.create_task(
            order_service.submit_order_to_alipos(submission_db, order)
        )
        try:
            await asyncio.wait_for(request_started.wait(), timeout=1)

            response = await client.post(
                "/api/webhooks/order-status",
                json={
                    "eatsId": order.alipos_eats_id,
                    "status": "ACCEPTED_BY_RESTAURANT",
                    "orderNumber": "A-43",
                },
                headers={"clientId": "client", "clientSecret": "secret"},
            )
            assert response.status_code == 200
            assert webhook_session_ids[-1] != id(submission_db)
            async with sessions() as observer_db:
                persisted = await observer_db.get(Order, order.id)
                assert persisted is not None
                assert persisted.status == "ACCEPTED_BY_RESTAURANT"
                assert persisted.order_number == "A-43"
            assert order.status == "PAID_AWAITING_RESTAURANT"
            assert order.order_number is None

            release_request.set()
            await submit
            assert await order_service._submit_queued_alipos_order(
                submission_db,
                order.id,
            ) is None

            request.assert_awaited_once()
            refund.assert_not_awaited()
            assert order.alipos_sync_status == "unknown"
            assert order.payment_status == "paid"
            assert order.refund_sync_status is None
            assert order.status == "ACCEPTED_BY_RESTAURANT"
            assert order.order_number == "A-43"
        finally:
            release_request.set()
            if not submit.done():
                await asyncio.gather(submit, return_exceptions=True)


def _signed_callback(
    order: Order,
    *,
    amount: int | None = None,
    store_id: int = 42,
    payment_uuid: str = "payment-uuid",
) -> dict:
    callback_amount = amount if amount is not None else int(order.total_amount * 100)
    raw = f"{store_id}{order.id}{callback_amount}{settings.multicard_secret}"
    return {
        "store_id": store_id,
        "invoice_id": str(order.id),
        "amount": callback_amount,
        "sign": hashlib.md5(raw.encode()).hexdigest(),
        "uuid": payment_uuid,
        "receipt_url": "https://pay.example/receipt",
        "card_pan": "8600********1234",
        "ps": "UZCARD",
    }


@pytest.mark.asyncio
async def test_multicard_callback_queues_exact_paid_order_once(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    first = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order),
    )
    second = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order),
    )
    await webhook_db_session.refresh(order)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {}
    assert second.json() == {}
    assert order.payment_status == "paid"
    assert order.status == "PAID_AWAITING_RESTAURANT"
    assert order.alipos_sync_status == "queued"
    dispatch.assert_awaited_once_with(order.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("payment_status", ["invoice_queued", "invoice_unknown"])
async def test_multicard_callback_accepts_pre_checkout_invoice_states(
    client,
    webhook_db_session,
    monkeypatch,
    payment_status,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    order.payment_status = payment_status
    order.status = "PAYMENT_REVIEW"
    if payment_status == "invoice_unknown":
        order.multicard_invoice_uuid = "payment-uuid"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 200
    assert order.payment_status == "paid"
    assert order.status == "PAID_AWAITING_RESTAURANT"
    assert order.alipos_sync_status == "queued"
    dispatch.assert_awaited_once_with(order.id)


@pytest.mark.asyncio
async def test_multicard_callback_rejects_mismatched_known_invoice_uuid(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    order.payment_status = "invoice_unknown"
    order.status = "PAYMENT_REVIEW"
    order.multicard_invoice_uuid = "expected-invoice"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order, payment_uuid="different-invoice"),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 409
    assert order.payment_status == "invoice_unknown"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_wins_invoice_create_finalizer_race(
    client,
    webhook_race_sessions,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    sessions, created_user_ids, _ = webhook_race_sessions
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    async def rejected_after_callback(**_kwargs):
        provider_started.set()
        await release_provider.wait()
        raise order_service.multicard_api.InvoiceRejected(400)

    monkeypatch.setattr(
        order_service.multicard_api,
        "create_invoice",
        rejected_after_callback,
    )

    async with sessions() as invoice_db:
        order = await _pending_online_order(invoice_db)
        created_user_ids.append(order.user_id)
        order.payment_status = "invoice_queued"
        order.status = "PAYMENT_REVIEW"
        await invoice_db.commit()
        create_task = asyncio.create_task(
            order_service._create_order_invoice(invoice_db, order)
        )
        try:
            await asyncio.wait_for(provider_started.wait(), timeout=1)
            async with sessions() as observer_db:
                sending = await observer_db.get(Order, order.id)
                assert sending is not None
                assert sending.payment_status == "invoice_sending"

            response = await client.post(
                "/api/webhooks/multicard/callback",
                json=_signed_callback(order),
            )
            assert response.status_code == 200
            release_provider.set()
            await create_task
        finally:
            release_provider.set()
            if not create_task.done():
                await asyncio.gather(create_task, return_exceptions=True)

    async with sessions() as inspect_db:
        persisted = await inspect_db.get(Order, order.id)
        assert persisted is not None
        assert persisted.payment_status == "paid"
        assert persisted.status == "PAID_AWAITING_RESTAURANT"
        assert persisted.multicard_payment_uuid == "payment-uuid"
        assert persisted.alipos_sync_status == "queued"
    dispatch.assert_awaited_once_with(order.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("restaurant_status", "initial_sync_status"),
    [("NEW", None), ("ACCEPTED_BY_RESTAURANT", "synced")],
)
async def test_legacy_pending_delivery_callback_marks_paid_without_second_alipos_create(
    client,
    webhook_db_session,
    monkeypatch,
    restaurant_status,
    initial_sync_status,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    alipos_order_id = uuid.uuid4()
    order.discriminator = "delivery"
    order.table_id = None
    order.status = restaurant_status
    order.alipos_order_id = alipos_order_id
    order.alipos_sync_status = initial_sync_status
    order.multicard_invoice_uuid = "payment-uuid"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    create = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)
    monkeypatch.setattr(order_service.alipos_api, "create_order", create)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 200
    assert order.payment_status == "paid"
    assert order.alipos_sync_status == "synced"
    assert order.status == restaurant_status
    assert order.alipos_order_id == alipos_order_id
    dispatch.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payment_status", "refund_sync_status"),
    [("refund_pending", "queued"), ("refunded", "refunded")],
)
async def test_multicard_callback_acknowledges_refund_lifecycle_duplicate(
    client,
    webhook_db_session,
    monkeypatch,
    payment_status,
    refund_sync_status,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    order.payment_status = payment_status
    order.multicard_payment_uuid = "payment-uuid"
    order.refund_sync_status = refund_sync_status
    order.alipos_sync_status = "failed"
    order.status = "SUBMISSION_FAILED"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    refund = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)
    monkeypatch.setattr(webhooks_router.multicard_api, "refund_payment", refund)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 200
    assert response.json() == {}
    assert order.payment_status == payment_status
    assert order.refund_sync_status == refund_sync_status
    assert order.alipos_sync_status == "failed"
    assert order.status == "SUBMISSION_FAILED"
    dispatch.assert_not_awaited()
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_multicard_processed_callback_rejects_mismatched_payment_uuid(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    order.payment_status = "refunded"
    order.multicard_payment_uuid = "payment-uuid"
    order.refund_sync_status = "refunded"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order, payment_uuid="different-payment-uuid"),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 409
    assert response.json()["detail"] == "Payment identifier does not match order"
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_multicard_paid_duplicate_still_validates_expected_amount(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    order.payment_status = "paid"
    order.multicard_payment_uuid = "payment-uuid"
    await webhook_db_session.commit()
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order, amount=int(order.total_amount * 100) + 1),
    )

    await webhook_db_session.refresh(order)
    assert response.status_code == 400
    assert response.json()["detail"] == "Payment amount does not match order"
    assert order.payment_status == "paid"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_multicard_callback_amount_mismatch_does_not_mark_paid(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order, amount=int(order.total_amount * 100) + 1),
    )
    await webhook_db_session.refresh(order)

    assert response.status_code == 400
    assert order.payment_status == "pending"
    assert order.alipos_sync_status == "awaiting_payment"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_multicard_callback_wrong_store_does_not_mark_paid(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    dispatch = AsyncMock()
    monkeypatch.setattr(webhooks_router, "dispatch_queued_alipos_order", dispatch)

    response = await client.post(
        "/api/webhooks/multicard/callback",
        json=_signed_callback(order, store_id=99),
    )
    await webhook_db_session.refresh(order)

    assert response.status_code == 400
    assert order.payment_status == "pending"
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_multicard_callback_without_payment_uuid_is_rejected(
    client,
    webhook_db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "multicard_store_id", 42)
    monkeypatch.setattr(settings, "multicard_secret", "callback-secret")
    order = await _pending_online_order(webhook_db_session)
    body = _signed_callback(order)
    body.pop("uuid")

    response = await client.post("/api/webhooks/multicard/callback", json=body)
    await webhook_db_session.refresh(order)

    assert response.status_code == 400
    assert order.payment_status == "pending"


@pytest.mark.asyncio
async def test_register_telegram_webhook_skips_when_url_matches(monkeypatch):
    monkeypatch.setattr(
        settings, "public_backend_url", "https://restaurant.labtutor.app"
    )
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret")

    webhook_info_response = Mock()
    webhook_info_response.raise_for_status = Mock()
    webhook_info_response.json.return_value = {
        "ok": True,
        "result": {
            "url": "https://restaurant.labtutor.app/api/webhooks/bot",
            "allowed_updates": ["message"],
        },
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=webhook_info_response)
    client.post = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    with patch("app.main.httpx.AsyncClient", return_value=client):
        await register_telegram_webhook()

    client.get.assert_awaited_once()
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_telegram_webhook_sets_when_url_differs(monkeypatch):
    monkeypatch.setattr(
        settings, "public_backend_url", "https://restaurant.labtutor.app"
    )
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret")

    webhook_info_response = Mock()
    webhook_info_response.raise_for_status = Mock()
    webhook_info_response.json.return_value = {
        "ok": True,
        "result": {
            "url": "https://old.example.com/api/webhooks/bot",
            "allowed_updates": ["message"],
        },
    }

    set_webhook_response = Mock()
    set_webhook_response.raise_for_status = Mock()

    client = AsyncMock()
    client.get = AsyncMock(return_value=webhook_info_response)
    client.post = AsyncMock(return_value=set_webhook_response)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    with patch("app.main.httpx.AsyncClient", return_value=client):
        await register_telegram_webhook()

    client.post.assert_awaited_once_with(
        "https://api.telegram.org/botbot-token/setWebhook",
        json={
            "url": "https://restaurant.labtutor.app/api/webhooks/bot",
            "allowed_updates": ["message"],
            "secret_token": "secret",
        },
        timeout=10,
    )


@pytest.mark.asyncio
async def test_register_telegram_webhook_sets_when_allowed_updates_differ(monkeypatch):
    monkeypatch.setattr(
        settings, "public_backend_url", "https://restaurant.labtutor.app"
    )
    monkeypatch.setattr(settings, "public_app_url", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "secret")

    webhook_info_response = Mock()
    webhook_info_response.raise_for_status = Mock()
    webhook_info_response.json.return_value = {
        "ok": True,
        "result": {
            "url": "https://restaurant.labtutor.app/api/webhooks/bot",
            "allowed_updates": ["message", "callback_query"],
        },
    }

    set_webhook_response = Mock()
    set_webhook_response.raise_for_status = Mock()

    client = AsyncMock()
    client.get = AsyncMock(return_value=webhook_info_response)
    client.post = AsyncMock(return_value=set_webhook_response)
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    with patch("app.main.httpx.AsyncClient", return_value=client):
        await register_telegram_webhook()

    client.post.assert_awaited_once()
