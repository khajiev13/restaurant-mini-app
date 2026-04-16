from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.config import settings
from app.main import register_telegram_webhook
from app.models.models import User


@pytest.mark.asyncio
async def test_telegram_bot_webhook_updates_phone_number(client, db_session, monkeypatch, caplog):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")
    user = User(
        telegram_id=12345678,
        first_name="Test",
        last_name=None,
        username="tester",
    )
    db_session.add(user)
    await db_session.commit()

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

    await db_session.refresh(user)

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
async def test_telegram_bot_webhook_ignores_unknown_user(client, monkeypatch, caplog):
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
