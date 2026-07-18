import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import Order, User
from app.routers.tables import table_access
from app.services.table_access_service import TableDirectoryEntry

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
DIRECTORY_ENTRY = TableDirectoryEntry(
    table_id=TABLE_ID,
    table_title="Stol 12",
    hall_id=HALL_ID,
    hall_title="Asosiy zal",
    service_percent=10,
    manual_code="12",
)
DUPLICATE_DIRECTORY_RESPONSE = {
    "halls": DIRECTORY_RESPONSE["halls"],
    "tables": [
        *DIRECTORY_RESPONSE["tables"],
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "title": "Stol 012",
            "hallId": str(HALL_ID),
        },
    ],
}


@pytest.mark.asyncio
async def test_resolve_table_start_parameter_returns_customer_safe_context(client):
    start_param = table_access.build_start_param(DIRECTORY_ENTRY)

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
    assert data["manual_code"] == "12"
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
async def test_resolve_table_normalizes_manual_code(client):
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        response = await client.post("/api/tables/resolve", json={"code": "000012"})

    assert response.status_code == 200
    assert response.json()["data"]["manual_code"] == "12"


@pytest.mark.asyncio
async def test_resolve_table_accepts_legacy_start_parameter(client):
    start_param = table_access.build_legacy_start_param(TABLE_ID)

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        response = await client.post("/api/tables/resolve", json={"entry": start_param})

    assert response.status_code == 200
    assert response.json()["data"]["manual_code"] == "12"


@pytest.mark.asyncio
async def test_resolve_table_rejects_tampered_numeric_start_parameter(client):
    start_param = table_access.build_start_param(DIRECTORY_ENTRY)
    replacement = "0" if start_param[-1] != "0" else "1"

    response = await client.post(
        "/api/tables/resolve",
        json={"entry": start_param[:-1] + replacement},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid table QR"


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
    assert item["manual_code"] == "12"
    assert item["deep_link"].startswith("https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_")


@pytest.mark.asyncio
async def test_restore_table_context_from_owned_order_without_exposing_ids(
    client,
    db_session,
):
    user = User(
        telegram_id=7003,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=user.telegram_id,
        items=[],
        items_cost=10000,
        total_amount=11000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="inplace",
        table_id=TABLE_ID,
        table_title="Stol 12",
        hall_id=HALL_ID,
        hall_title="Asosiy zal",
        service_percent=10,
        table_access_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        + datetime.timedelta(hours=1),
        status="NEW",
    )
    db_session.add_all([user, order])
    await db_session.commit()

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DIRECTORY_RESPONSE),
    ):
        response = await client.post(
            f"/api/tables/restore/{order.id}",
            headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["table_title"] == "Stol 12"
    assert data["access_token"].startswith("ta1.")
    restored_claims = table_access.verify_access_token(data["access_token"])
    expected_expiry = order.table_access_expires_at.replace(tzinfo=datetime.UTC)
    assert restored_claims.expires_at == expected_expiry.replace(microsecond=0)
    assert str(TABLE_ID) not in response.text
    assert str(HALL_ID) not in response.text


@pytest.mark.asyncio
async def test_restore_rejects_an_expired_table_session(client, db_session):
    user = User(
        telegram_id=7004,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=user.telegram_id,
        items=[],
        items_cost=10000,
        total_amount=11000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="inplace",
        table_id=TABLE_ID,
        table_access_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        - datetime.timedelta(seconds=1),
        status="NEW",
    )
    db_session.add_all([user, order])
    await db_session.commit()

    response = await client.post(
        f"/api/tables/restore/{order.id}",
        headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resolve_returns_generic_503_for_duplicate_numeric_directory(client):
    start_param = table_access.build_start_param(DIRECTORY_ENTRY)

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DUPLICATE_DIRECTORY_RESPONSE),
    ):
        response = await client.post("/api/tables/resolve", json={"entry": start_param})

    assert response.status_code == 503
    assert response.json()["detail"] == "Table directory is temporarily unavailable"
    assert str(TABLE_ID) not in response.text


@pytest.mark.asyncio
async def test_restore_returns_generic_503_for_duplicate_numeric_directory(client, db_session):
    user = User(
        telegram_id=7005,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=user.telegram_id,
        items=[],
        items_cost=10000,
        total_amount=11000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="inplace",
        table_id=TABLE_ID,
        table_access_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        + datetime.timedelta(hours=1),
        status="NEW",
    )
    db_session.add_all([user, order])
    await db_session.commit()

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DUPLICATE_DIRECTORY_RESPONSE),
    ):
        response = await client.post(
            f"/api/tables/restore/{order.id}",
            headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Table directory is temporarily unavailable"
    assert str(TABLE_ID) not in response.text


@pytest.mark.asyncio
async def test_manifest_returns_generic_503_for_duplicate_numeric_directory(client, db_session):
    admin = User(
        telegram_id=7006,
        first_name="Admin",
        last_name=None,
        username=None,
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=DUPLICATE_DIRECTORY_RESPONSE),
    ):
        response = await client.get(
            "/api/tables/manifest",
            headers={"Authorization": f"Bearer {create_jwt(admin.telegram_id)}"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Table directory is temporarily unavailable"
    assert str(TABLE_ID) not in response.text
