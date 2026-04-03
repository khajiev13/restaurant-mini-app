from unittest.mock import patch

import pytest

FAKE_USER = {"id": 777001, "first_name": "Addr", "last_name": None, "username": "addruser"}


async def _get_token(client) -> str:
    with patch("app.routers.auth.validate_init_data", return_value=FAKE_USER):
        r = await client.post("/api/auth/telegram", json={"init_data": "mocked"})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_list_addresses_unauthenticated(client):
    response = await client.get("/api/addresses")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_addresses_empty(client):
    token = await _get_token(client)
    response = await client.get("/api/addresses", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_create_and_list_address(client):
    token = await _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "label": "Home",
        "full_address": "Navoi 15/2",
        "entrance": "1",
        "floor": "3",
        "apartment": "5A",
        "door_code": "",
        "instructions": "",
        "lat": 41.2995,
        "lng": 69.2401,
    }

    create_resp = await client.post("/api/addresses", json=payload, headers=headers)
    assert create_resp.status_code in (200, 201)
    created = create_resp.json()["data"]
    assert created["label"] == "Home"
    assert created["full_address"] == "Navoi 15/2"

    list_resp = await client.get("/api/addresses", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1


@pytest.mark.asyncio
async def test_delete_address(client):
    token = await _get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"label": "Work", "full_address": "Amir Temur 108", "entrance": "", "floor": "", "apartment": "", "door_code": "", "instructions": "", "lat": None, "lng": None}
    create_resp = await client.post("/api/addresses", json=payload, headers=headers)
    address_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(f"/api/addresses/{address_id}", headers=headers)
    assert delete_resp.status_code in (200, 204)

    list_resp = await client.get("/api/addresses", headers=headers)
    assert list_resp.json()["data"] == []
