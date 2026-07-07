import datetime
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
async def test_telegram_bot_webhook_ignores_messages_without_contact(client, monkeypatch, caplog):
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
async def test_telegram_bot_webhook_ignores_unknown_user(client, webhook_db_session, monkeypatch, caplog):
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

    user = User(telegram_id=telegram_id, first_name="Customer", last_name=None, username=None)
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


@pytest.mark.asyncio
async def test_register_telegram_webhook_skips_when_url_matches(monkeypatch):
    monkeypatch.setattr(settings, "public_backend_url", "https://restaurant.labtutor.app")
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
    monkeypatch.setattr(settings, "public_backend_url", "https://restaurant.labtutor.app")
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
    monkeypatch.setattr(settings, "public_backend_url", "https://restaurant.labtutor.app")
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
