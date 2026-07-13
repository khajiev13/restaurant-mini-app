import datetime
import hashlib
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.config import settings
from app.main import register_telegram_webhook
from app.models.models import Order, User
from app.routers import webhooks as webhooks_router


@pytest.fixture
def webhook_db_session(db_session, monkeypatch):
    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(webhooks_router, "async_session", _session_override)
    return db_session


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


def _signed_callback(
    order: Order, *, amount: int | None = None, store_id: int = 42
) -> dict:
    callback_amount = amount if amount is not None else int(order.total_amount * 100)
    raw = f"{store_id}{order.id}{callback_amount}{settings.multicard_secret}"
    return {
        "store_id": store_id,
        "invoice_id": str(order.id),
        "amount": callback_amount,
        "sign": hashlib.md5(raw.encode()).hexdigest(),
        "uuid": "payment-uuid",
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
