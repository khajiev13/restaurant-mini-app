import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import User
from app.routers.tables import table_access

TABLE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
HALL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
DIRECTORY_RESPONSE = {
    "halls": [
        {"id": str(HALL_ID), "title": "Asosiy zal", "servicePercent": 10},
    ],
    "tables": [
        {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)},
    ],
}


@pytest.mark.asyncio
async def test_resolve_table_start_parameter_returns_customer_safe_context(client):
    start_param = table_access.build_start_param(TABLE_ID)

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        response = await client.post("/api/tables/resolve", json={"entry": start_param})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["table_title"] == "Stol 12"
    assert data["hall_title"] == "Asosiy zal"
    assert data["service_percent"] == 10
    assert data["manual_code"] == table_access.build_manual_code(TABLE_ID)
    assert str(TABLE_ID) not in response.text


@pytest.mark.asyncio
async def test_resolve_table_rejects_unknown_manual_code(client):
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        response = await client.post("/api/tables/resolve", json={"code": "ZZZZZZ"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Table code was not found"


@pytest.mark.asyncio
async def test_table_manifest_requires_admin_and_returns_deep_links(client, db_session):
    customer = User(
        telegram_id=7001,
        first_name="Customer",
        last_name=None,
        username=None,
        role="customer",
    )
    admin = User(
        telegram_id=7002,
        first_name="Admin",
        last_name=None,
        username=None,
        role="admin",
    )
    db_session.add_all([customer, admin])
    await db_session.commit()

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        forbidden = await client.get(
            "/api/tables/manifest",
            headers={"Authorization": f"Bearer {create_jwt(customer.telegram_id)}"},
        )
        allowed = await client.get(
            "/api/tables/manifest",
            headers={"Authorization": f"Bearer {create_jwt(admin.telegram_id)}"},
        )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    item = allowed.json()["data"][0]
    assert item["table_title"] == "Stol 12"
    assert item["manual_code"] == table_access.build_manual_code(TABLE_ID)
    assert item["deep_link"].startswith("https://t.me/olotsomsa_zakaz_bot?startapp=t_")
