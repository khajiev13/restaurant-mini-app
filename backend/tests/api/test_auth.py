from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_auth_missing_body(client):
    response = await client.post("/api/auth/telegram", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_auth_invalid_init_data(client):
    response = await client.post("/api/auth/telegram", json={"init_data": "invalid"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_creates_user_and_returns_token(client):
    fake_user = {"id": 999999, "first_name": "Test", "last_name": "User", "username": "testuser"}

    with patch("app.routers.auth.validate_init_data", return_value=fake_user):
        response = await client.post("/api/auth/telegram", json={"init_data": "mocked"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]


@pytest.mark.asyncio
async def test_auth_upserts_existing_user(client):
    fake_user = {"id": 999998, "first_name": "First", "last_name": None, "username": "upsertuser"}

    with patch("app.routers.auth.validate_init_data", return_value=fake_user):
        r1 = await client.post("/api/auth/telegram", json={"init_data": "mocked"})
        assert r1.status_code == 200

    fake_user["first_name"] = "Updated"
    with patch("app.routers.auth.validate_init_data", return_value=fake_user):
        r2 = await client.post("/api/auth/telegram", json={"init_data": "mocked"})
        assert r2.status_code == 200
        assert "access_token" in r2.json()["data"]


@pytest.mark.asyncio
async def test_auth_bootstraps_configured_admin(client, monkeypatch):
    fake_user = {
        "id": 424242,
        "first_name": "Admin",
        "last_name": "User",
        "username": "adminuser",
    }
    monkeypatch.setattr("app.config.settings.bootstrap_admin_telegram_ids", "424242")

    with patch("app.routers.auth.validate_init_data", return_value=fake_user):
        auth_response = await client.post("/api/auth/telegram", json={"init_data": "mocked"})

    token = auth_response.json()["data"]["access_token"]
    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert auth_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["data"]["role"] == "admin"
