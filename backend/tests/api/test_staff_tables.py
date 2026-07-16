import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import Order, User
from app.services import alipos_api

TABLE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TABLE_2_ID = uuid.UUID("11111111-1111-4111-8111-111111111112")
HALL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
PAYMENT_UUID_CANARY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(user.telegram_id)}"}


async def create_user(
    db_session,
    telegram_id: int,
    role: str,
    phone: str | None = None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        username=f"user{telegram_id}",
        phone_number=phone,
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def directory_snapshot(
    *,
    two_tables: bool = False,
    stale: bool = False,
    last_success_at: datetime.datetime | None = None,
) -> alipos_api.HallsTablesSnapshot:
    tables = [{"id": str(TABLE_ID), "title": "Stol 1", "hallId": str(HALL_ID)}]
    if two_tables:
        tables.append(
            {"id": str(TABLE_2_ID), "title": "Stol 2", "hallId": str(HALL_ID)}
        )
    return alipos_api.HallsTablesSnapshot(
        payload={
            "halls": [
                {
                    "id": str(HALL_ID),
                    "title": "Asosiy zal",
                    "servicePercent": 10,
                }
            ],
            "tables": tables,
        },
        stale=stale,
        last_success_at=last_success_at or datetime.datetime.now(datetime.UTC),
    )


async def create_table_order(
    db_session,
    customer: User,
    *,
    sync: str,
    total: int,
    table_id: uuid.UUID = TABLE_ID,
    status: str = "NEW",
    payment_method: str = "cash",
    payment_status: str | None = None,
    refund_sync_status: str | None = None,
    refund_sync_error: str | None = None,
    multicard_payment_uuid: str | None = None,
    items: list[dict] | None = None,
    attempted_at: datetime.datetime | None = None,
    checked_at: datetime.datetime | None = None,
) -> Order:
    order = Order(
        user_id=customer.telegram_id,
        items=items
        or [
            {
                "id": "somsa",
                "name": "Classic Somsa",
                "quantity": 1,
                "price": 18000,
                "modifications": [],
            }
        ],
        items_cost=18000,
        total_amount=total,
        delivery_fee=0,
        payment_method=payment_method,
        payment_status=payment_status,
        refund_sync_status=refund_sync_status,
        refund_sync_error=refund_sync_error,
        multicard_payment_uuid=multicard_payment_uuid,
        discriminator="inplace",
        table_id=table_id,
        table_title="Stol 1" if table_id == TABLE_ID else "Removed 9",
        hall_id=HALL_ID,
        hall_title="Asosiy zal",
        service_percent=10,
        alipos_order_id=uuid.uuid4() if sync == "synced" else None,
        alipos_sync_status=sync,
        status=status,
        alipos_status_check_attempted_at=attempted_at,
        alipos_status_checked_at=checked_at,
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_refund_states_are_normalized_without_repeating_provider_mutations(
    client,
    db_session,
):
    staff = await create_user(db_session, 8100, "staff")
    customer = await create_user(
        db_session,
        8101,
        "customer",
        phone="+998-provider-customer-canary",
    )
    unknown = await create_table_order(
        db_session,
        customer,
        sync="unknown",
        status="provider-status-canary",
        total=19800,
        payment_method="rahmat",
        payment_status="paid",
        multicard_payment_uuid=PAYMENT_UUID_CANARY,
    )
    completed = await create_table_order(
        db_session,
        customer,
        sync="failed",
        status="SUBMISSION_FAILED",
        total=19800,
        payment_method="rahmat",
        payment_status="refunded",
        refund_sync_status="refunded",
    )
    pending_orders = [
        await create_table_order(
            db_session,
            customer,
            sync="failed",
            status="SUBMISSION_FAILED",
            total=19800,
            payment_method="rahmat",
            payment_status="refund_pending",
            refund_sync_status=refund_state,
            refund_sync_error="provider-refund-body-canary",
        )
        for refund_state in ("queued", "sending")
    ]
    ambiguous = await create_table_order(
        db_session,
        customer,
        sync="failed",
        status="SUBMISSION_FAILED",
        total=19800,
        payment_method="rahmat",
        payment_status="refund_pending",
        refund_sync_status="unknown",
        refund_sync_error="provider-refund-body-canary",
    )
    failed = await create_table_order(
        db_session,
        customer,
        sync="failed",
        status="SUBMISSION_FAILED",
        total=19800,
        payment_method="rahmat",
        payment_status="refund_failed",
        refund_sync_status="failed",
        refund_sync_error="provider-refund-body-canary",
    )
    cash = await create_table_order(
        db_session,
        customer,
        sync="failed",
        status="SUBMISSION_FAILED",
        total=19800,
    )
    create_mutation = AsyncMock()
    refund_mutation = AsyncMock()

    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(return_value=directory_snapshot()),
        ),
        patch("app.services.alipos_api.create_order", new=create_mutation),
        patch("app.services.multicard_api.refund_payment", new=refund_mutation),
    ):
        response = await client.get(
            f"/api/staff/tables/{TABLE_ID}",
            headers=auth_headers(staff),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    orders = {order["id"]: order for order in data["orders"]}
    assert str(completed.id) not in orders
    assert orders[str(unknown.id)]["sync_label"] == "verify_in_pos"
    assert orders[str(unknown.id)]["payment_status"] == "paid"
    for order in pending_orders:
        assert orders[str(order.id)]["payment_status"] == "refund_pending"
    assert orders[str(ambiguous.id)]["payment_status"] == "refund_verification_required"
    assert orders[str(failed.id)]["payment_status"] == "refund_failed"
    assert orders[str(cash.id)]["payment_status"] is None
    assert data["table"]["synchronized_order_count"] == 0
    assert data["table"]["attention_order_count"] == 6
    assert data["table"]["combined_items"] == []
    assert data["table"]["total_amount"] == 0
    for canary in (
        "provider-status-canary",
        PAYMENT_UUID_CANARY,
        "provider-refund-body-canary",
        "+998-provider-customer-canary",
    ):
        assert canary not in response.text
    create_mutation.assert_not_awaited()
    refund_mutation.assert_not_awaited()


@pytest.mark.asyncio
async def test_customer_is_denied_but_staff_and_admin_can_list_tables(
    client, db_session
):
    customer = await create_user(db_session, 8101, "customer")
    staff = await create_user(db_session, 8102, "staff")
    admin = await create_user(db_session, 8103, "admin")
    directory = AsyncMock(return_value=directory_snapshot())

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=directory,
    ):
        denied = await client.get("/api/staff/tables", headers=auth_headers(customer))
        allowed_staff = await client.get(
            "/api/staff/tables", headers=auth_headers(staff)
        )
        allowed_admin = await client.get(
            "/api/staff/tables", headers=auth_headers(admin)
        )

    assert denied.status_code == 403
    assert allowed_staff.status_code == 200
    assert allowed_admin.status_code == 200
    assert directory.await_count == 2


@pytest.mark.asyncio
async def test_directory_provider_runs_without_request_database_transaction(
    client, db_session
):
    staff = await create_user(db_session, 8104, "staff")
    await db_session.commit()

    async def directory_provider() -> alipos_api.HallsTablesSnapshot:
        assert not db_session.in_transaction()
        return directory_snapshot()

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(side_effect=directory_provider),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_overview_returns_all_tables_and_aggregates_only_synced_orders(
    client, db_session
):
    staff = await create_user(db_session, 8110, "staff")
    customer = await create_user(db_session, 8111, "customer")
    await create_table_order(db_session, customer, sync="synced", total=19800)
    await create_table_order(db_session, customer, sync="sending", total=22000)

    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(return_value=directory_snapshot(two_tables=True)),
        ),
        patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=AsyncMock(
                return_value={"status": "NEW", "updatedAt": "2026-07-15T09:00:00Z"}
            ),
        ),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    tables = response.json()["data"]["halls"][0]["tables"]
    assert response.status_code == 200
    assert len(tables) == 2
    assert tables[0]["synchronized_order_count"] == 1
    assert tables[0]["processing_order_count"] == 1
    assert tables[0]["total_amount"] == 19800
    assert tables[1]["synchronized_order_count"] == 0


@pytest.mark.asyncio
async def test_detail_omits_customer_and_provider_sensitive_data(client, db_session):
    staff = await create_user(db_session, 8120, "staff")
    customer = await create_user(db_session, 8121, "customer", phone="+998901112233")
    order = await create_table_order(db_session, customer, sync="synced", total=19800)

    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(return_value=directory_snapshot()),
        ),
        patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=AsyncMock(
                return_value={"status": "NEW", "updatedAt": "2026-07-15T09:00:00Z"}
            ),
        ),
    ):
        response = await client.get(
            f"/api/staff/tables/{order.table_id}",
            headers=auth_headers(staff),
        )

    assert response.status_code == 200
    for forbidden in (
        "+998901112233",
        "telegram_id",
        "table_access",
        "multicard",
        "alipos_sync_error",
        "payment_card_pan",
    ):
        assert forbidden not in response.text


@pytest.mark.asyncio
async def test_no_directory_and_no_cache_returns_503_before_status_reads(
    client, db_session
):
    staff = await create_user(db_session, 8130, "staff")
    customer = await create_user(db_session, 8131, "customer")
    await create_table_order(db_session, customer, sync="synced", total=19800)
    status_read = AsyncMock()
    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(side_effect=alipos_api.HallsTablesUnavailable()),
        ),
        patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=status_read,
        ),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    assert response.status_code == 503
    assert response.json()["detail"] == "Table directory is temporarily unavailable"
    status_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_empty_unlisted_and_not_found_directory_paths(client, db_session):
    staff = await create_user(db_session, 8140, "staff")
    customer = await create_user(db_session, 8141, "customer")
    removed_id = uuid.UUID("99999999-9999-4999-8999-999999999999")
    now = datetime.datetime.now(datetime.UTC)
    await create_table_order(
        db_session,
        customer,
        sync="sending",
        total=19800,
        table_id=removed_id,
    )

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=directory_snapshot(stale=True, last_success_at=now)),
    ):
        stale = await client.get("/api/staff/tables", headers=auth_headers(staff))
        missing = await client.get(
            "/api/staff/tables/88888888-8888-4888-8888-888888888888",
            headers=auth_headers(staff),
        )

    assert stale.status_code == 200
    assert stale.json()["data"]["freshness"]["directory_stale"] is True
    unlisted = stale.json()["data"]["halls"][-1]
    assert unlisted["is_listed"] is False
    assert unlisted["tables"][0]["table_title"] == "Removed 9"
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_valid_empty_directory_returns_200_without_fabricating_local_tables(
    client, db_session
):
    staff = await create_user(db_session, 8150, "staff")
    now = datetime.datetime.now(datetime.UTC)
    snapshot = alipos_api.HallsTablesSnapshot(
        payload={"halls": [], "tables": []},
        stale=False,
        last_success_at=now,
    )
    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    assert response.status_code == 200
    assert response.json()["data"]["halls"] == []


@pytest.mark.asyncio
async def test_partial_status_failure_keeps_cached_order_and_removes_new_terminal(
    client, db_session
):
    staff = await create_user(db_session, 8160, "staff")
    customer = await create_user(db_session, 8161, "customer")
    failed = await create_table_order(db_session, customer, sync="synced", total=19800)
    terminal = await create_table_order(
        db_session, customer, sync="synced", total=22000
    )

    async def status_side_effect(alipos_id: str) -> dict:
        if alipos_id == str(failed.alipos_order_id):
            raise RuntimeError("provider unavailable")
        assert alipos_id == str(terminal.alipos_order_id)
        return {"status": "DELIVERED", "updatedAt": "2026-07-15T09:00:00Z"}

    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(return_value=directory_snapshot()),
        ),
        patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=AsyncMock(side_effect=status_side_effect),
        ),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    table = response.json()["data"]["halls"][0]["tables"][0]
    assert response.status_code == 200
    assert table["synchronized_order_count"] == 1
    assert response.json()["data"]["freshness"]["order_status_stale"] is True
    await db_session.refresh(terminal)
    assert terminal.status == "DELIVERED"


@pytest.mark.asyncio
async def test_newer_attempt_than_success_marks_cached_status_stale(client, db_session):
    staff = await create_user(db_session, 8170, "staff")
    customer = await create_user(db_session, 8171, "customer")
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    await create_table_order(
        db_session,
        customer,
        sync="synced",
        total=19800,
        attempted_at=now,
        checked_at=now - datetime.timedelta(seconds=5),
    )
    status_read = AsyncMock()

    with (
        patch(
            "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
            new=AsyncMock(return_value=directory_snapshot()),
        ),
        patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=status_read,
        ),
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    assert response.status_code == 200
    assert response.json()["data"]["freshness"]["order_status_stale"] is True
    status_read.assert_not_awaited()
