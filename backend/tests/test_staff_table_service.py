import asyncio
import datetime
import logging
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.models import Base, Order, User
from app.services.staff_table_service import (
    aggregate_order_items,
    build_staff_table_detail,
    build_staff_tables_overview,
    classify_table_order,
    reconcile_stale_table_orders,
)
from app.services.table_access_service import TableDirectoryEntry

TABLE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
HALL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def make_order(**overrides) -> Order:
    values = {
        "id": uuid.uuid4(),
        "user_id": 1,
        "items": [
            {
                "id": "somsa",
                "name": "Classic Somsa",
                "quantity": 1,
                "price": 18000,
                "modifications": [],
            }
        ],
        "items_cost": Decimal("18000"),
        "total_amount": Decimal("19800"),
        "delivery_fee": Decimal("0"),
        "payment_method": "cash",
        "payment_status": None,
        "discriminator": "inplace",
        "table_id": TABLE_ID,
        "table_title": "Stol 1",
        "hall_id": HALL_ID,
        "hall_title": "Asosiy zal",
        "service_percent": Decimal("10"),
        "alipos_sync_status": "synced",
        "status": "NEW",
        "created_at": datetime.datetime(2026, 7, 15, 9, 0),
    }
    values.update(overrides)
    return Order(**values)


def directory_entry() -> TableDirectoryEntry:
    return TableDirectoryEntry(
        table_id=TABLE_ID,
        table_title="Stol 1",
        hall_id=HALL_ID,
        hall_title="Asosiy zal",
        service_percent=Decimal("10"),
    )


def freshness():
    from app.schemas.staff_table import StaffTablesFreshnessResponse

    now = datetime.datetime(2026, 7, 15, 9, 1, tzinfo=datetime.UTC)
    return StaffTablesFreshnessResponse(
        generated_at=now,
        directory_stale=False,
        directory_last_success_at=now,
        order_status_stale=False,
        order_status_oldest_success_at=now,
    )


def test_classification_maps_visible_sync_states():
    assert classify_table_order(make_order()) == "synchronized"
    assert classify_table_order(make_order(alipos_sync_status="queued")) == "processing"
    assert (
        classify_table_order(make_order(alipos_sync_status="sending")) == "processing"
    )
    assert classify_table_order(make_order(alipos_sync_status="failed")) == "attention"
    assert classify_table_order(make_order(alipos_sync_status="unknown")) == "attention"


@pytest.mark.parametrize(
    ("status", "sync"),
    [
        ("DELIVERED", "synced"),
        ("CANCELLED", "synced"),
        ("CANCELED", "synced"),
        ("AWAITING_PAYMENT", "awaiting_payment"),
        ("PAYMENT_FAILED", "awaiting_payment"),
        ("PAYMENT_REVIEW", "awaiting_payment"),
    ],
)
def test_classification_excludes_terminal_and_pre_payment_orders(status, sync):
    assert (
        classify_table_order(make_order(status=status, alipos_sync_status=sync)) is None
    )


def test_online_order_requires_confirmed_payment_for_synced_or_processing():
    assert (
        classify_table_order(
            make_order(payment_method="rahmat", payment_status="pending")
        )
        is None
    )
    assert (
        classify_table_order(make_order(payment_method="rahmat", payment_status="paid"))
        == "synchronized"
    )


def test_aggregate_items_keeps_different_modifier_signatures_separate():
    plain = make_order()
    spicy = make_order(
        items=[
            {
                "id": "somsa",
                "name": "Classic Somsa",
                "quantity": 1,
                "price": 18000,
                "modifications": [
                    {"id": "spicy", "name": "Spicy", "quantity": 1, "price": 1000}
                ],
            }
        ]
    )

    items = aggregate_order_items([plain, plain, spicy])

    assert [(item.quantity, item.line_total) for item in items] == [
        (2.0, 36000.0),
        (1.0, 19000.0),
    ]


def test_aggregate_items_normalizes_decimal_spelling_and_modifier_order():
    first = make_order(
        items=[
            {
                "id": "combo",
                "name": "Combo",
                "quantity": 1,
                "price": 18000,
                "modifications": [
                    {"id": "a", "name": "A", "quantity": 1, "price": 500},
                    {"id": "b", "name": "B", "quantity": 1, "price": 1000},
                ],
            }
        ]
    )
    second = make_order(
        items=[
            {
                "id": "combo",
                "name": "Renamed copy",
                "quantity": "2.0",
                "price": "18000.0",
                "modifications": [
                    {
                        "id": "b",
                        "name": "B",
                        "quantity": "1.0",
                        "price": "1000.00",
                    },
                    {"id": "a", "name": "A", "quantity": "1", "price": "500.0"},
                ],
            }
        ]
    )

    items = aggregate_order_items([first, second])

    assert len(items) == 1
    assert items[0].quantity == 3
    assert items[0].line_total == 57000


def test_aggregate_items_splits_product_price_and_modifier_signature_changes():
    variants = [
        make_order(
            items=[
                {
                    "id": "a",
                    "name": "Same",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [],
                }
            ]
        ),
        make_order(
            items=[
                {
                    "id": "b",
                    "name": "Same",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [],
                }
            ]
        ),
        make_order(
            items=[
                {
                    "id": "a",
                    "name": "Same",
                    "quantity": 1,
                    "price": 101,
                    "modifications": [],
                }
            ]
        ),
        make_order(
            items=[
                {
                    "id": "a",
                    "name": "Same",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [{"id": "m", "quantity": 1, "price": 1}],
                }
            ]
        ),
        make_order(
            items=[
                {
                    "id": "a",
                    "name": "Same",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [{"id": "m", "quantity": 2, "price": 1}],
                }
            ]
        ),
        make_order(
            items=[
                {
                    "id": "a",
                    "name": "Same",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [{"id": "m", "quantity": 1, "price": 2}],
                }
            ]
        ),
    ]

    assert len(aggregate_order_items(variants)) == 6


def test_overview_aggregates_only_synchronized_orders_and_keeps_every_table():
    synced = make_order()
    processing = make_order(alipos_sync_status="sending")
    attention = make_order(alipos_sync_status="failed", status="SUBMISSION_FAILED")

    result = build_staff_tables_overview(
        [directory_entry()],
        [synced, processing, attention],
        freshness(),
    )
    table = result.halls[0].tables[0]

    assert table.synchronized_order_count == 1
    assert table.processing_order_count == 1
    assert table.attention_order_count == 1
    assert table.items_cost == 18000
    assert table.service_amount == 1800
    assert table.total_amount == 19800


def test_money_uses_persisted_order_totals_without_current_menu_repricing():
    persisted = make_order(
        items=[
            {
                "id": "legacy",
                "name": "Legacy",
                "quantity": 1,
                "price": 999,
                "modifications": [],
            }
        ],
        items_cost=Decimal("12345"),
        delivery_fee=Decimal("0"),
        total_amount=Decimal("13702"),
    )

    result = (
        build_staff_tables_overview([directory_entry()], [persisted], freshness())
        .halls[0]
        .tables[0]
    )

    assert result.items_cost == 12345
    assert result.service_amount == 1357
    assert result.total_amount == 13702


def test_overview_is_compact_but_detail_is_complete_and_preserves_orders():
    first = make_order(
        items=[
            {"id": "a", "name": "A", "quantity": 1, "price": 100, "modifications": []},
            {"id": "b", "name": "B", "quantity": 1, "price": 200, "modifications": []},
        ]
    )
    second = make_order(
        items=[
            {"id": "c", "name": "C", "quantity": 1, "price": 300, "modifications": []}
        ],
        items_cost=Decimal("300"),
        total_amount=Decimal("330"),
        created_at=datetime.datetime(2026, 7, 15, 9, 1),
    )

    overview = build_staff_tables_overview(
        [directory_entry()], [first, second], freshness()
    )
    detail = build_staff_table_detail(
        TABLE_ID, [directory_entry()], [first, second], freshness()
    )

    assert len(overview.halls[0].tables[0].combined_items) == 2
    assert overview.halls[0].tables[0].combined_line_count == 3
    assert detail is not None
    assert len(detail.table.combined_items) == 3
    assert [order.id for order in detail.orders] == [second.id, first.id]


def test_removed_active_table_uses_saved_snapshot_in_unlisted_group():
    order = make_order(
        table_title="Patio 9",
        hall_title="Old patio",
        service_percent=Decimal("12"),
    )

    overview = build_staff_tables_overview([], [order], freshness())

    assert overview.halls[0].is_listed is False
    assert overview.halls[0].hall_id is None
    assert overview.halls[0].tables[0].table_title == "Patio 9"
    assert overview.halls[0].tables[0].hall_title == "Old patio"
    assert overview.halls[0].tables[0].service_percent == 12


def test_detail_distinguishes_failed_from_unknown_without_raw_sync_payloads():
    failed = make_order(alipos_sync_status="failed", status="SUBMISSION_FAILED")
    unknown = make_order(alipos_sync_status="unknown", status="SYNC_UNKNOWN")

    detail = build_staff_table_detail(
        TABLE_ID, [directory_entry()], [failed, unknown], freshness()
    )

    assert detail is not None
    assert {order.sync_label for order in detail.orders} == {
        "not_synchronized",
        "verify_in_pos",
    }


def test_detail_contract_omits_customer_and_provider_sensitive_fields():
    detail = build_staff_table_detail(
        TABLE_ID,
        [directory_entry()],
        [make_order()],
        freshness(),
    )

    assert detail is not None
    payload = detail.model_dump(mode="json")

    def collect_keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(
                *(collect_keys(item) for item in value.values())
            )
        if isinstance(value, list):
            return set().union(*(collect_keys(item) for item in value), set())
        return set()

    forbidden = {
        "user_id",
        "telegram_id",
        "phone_number",
        "delivery_info",
        "table_access_expires_at",
        "multicard_invoice_uuid",
        "multicard_checkout_url",
        "multicard_payment_uuid",
        "alipos_sync_error",
        "payment_card_pan",
    }
    assert forbidden.isdisjoint(collect_keys(payload))
    assert set(payload["orders"][0]["items"][0]) == {
        "id",
        "name",
        "quantity",
        "price",
        "modifications",
    }


@pytest.mark.asyncio
async def test_reconcile_atomically_throttles_caps_concurrency_and_logs_safe_counts(
    caplog,
):
    test_database = f"codex_staff_tables_{uuid.uuid4().hex[:12]}"
    base_url = make_url(settings.database_url)
    admin_engine = create_async_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    engine = None
    try:
        async with admin_engine.connect() as admin:
            await admin.execute(text(f'CREATE DATABASE "{test_database}"'))

        engine = create_async_engine(
            base_url.set(database=test_database),
            poolclass=NullPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        telegram_id = 8_000_000_000 + uuid.uuid4().int % 900_000_000
        now = datetime.datetime.now(datetime.UTC)
        now_naive = now.replace(tzinfo=None)
        stale_provider_ids = [uuid.uuid4() for _ in range(6)]
        failed_provider_id = stale_provider_ids[-1]
        fresh_provider_id = uuid.uuid4()

        def persisted_order(**overrides) -> Order:
            values = {
                "user_id": telegram_id,
                "items": [
                    {
                        "id": "somsa",
                        "name": "Somsa",
                        "quantity": 1,
                        "price": 100,
                        "modifications": [],
                    }
                ],
                "items_cost": 100,
                "total_amount": 110,
                "delivery_fee": 0,
                "payment_method": "cash",
                "payment_status": None,
                "discriminator": "inplace",
                "table_id": TABLE_ID,
                "table_title": "Stol 1",
                "hall_id": HALL_ID,
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "alipos_sync_status": "synced",
                "status": "NEW",
            }
            values.update(overrides)
            return Order(**values)

        caplog.set_level(logging.INFO, logger="uvicorn.error")
        async with sessions() as setup:
            setup.add(
                User(
                    telegram_id=telegram_id,
                    first_name="Concurrency",
                    last_name=None,
                    username=None,
                    phone_number=None,
                    role="customer",
                )
            )
            setup.add_all(
                [
                    persisted_order(alipos_order_id=provider_id)
                    for provider_id in stale_provider_ids
                ]
            )
            setup.add(
                persisted_order(
                    alipos_order_id=fresh_provider_id,
                    alipos_status_check_attempted_at=now_naive,
                    alipos_status_checked_at=now_naive,
                )
            )
            setup.add(
                persisted_order(
                    alipos_order_id=uuid.uuid4(),
                    table_id=None,
                    table_title=None,
                )
            )
            setup.add(
                persisted_order(
                    alipos_order_id=uuid.uuid4(),
                    payment_method="rahmat",
                    payment_status="pending",
                )
            )
            await setup.commit()

        active = 0
        maximum_active = 0

        async def read_status(alipos_id: str) -> dict:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            try:
                await asyncio.sleep(0.01)
                if alipos_id == str(failed_provider_id):
                    raise RuntimeError("provider failure")
                return {
                    "status": "NEW",
                    "orderNumber": f"N-{alipos_id[-4:]}",
                    "updatedAt": "2026-07-15T09:00:00Z",
                }
            finally:
                active -= 1

        status_read = AsyncMock(side_effect=read_status)
        with patch(
            "app.services.staff_table_service.alipos_api.get_order_status",
            new=status_read,
        ):
            async with sessions() as worker_one, sessions() as worker_two:
                await asyncio.gather(
                    reconcile_stale_table_orders(worker_one, now),
                    reconcile_stale_table_orders(worker_two, now),
                )
            async with sessions() as repeated:
                await reconcile_stale_table_orders(repeated, now)

        assert status_read.await_count == 6
        assert maximum_active == 5
        assert {call.args[0] for call in status_read.await_args_list} == {
            str(value) for value in stale_provider_ids
        }

        async with sessions() as verify:
            rows = list(
                (
                    await verify.scalars(
                        select(Order).where(Order.user_id == telegram_id)
                    )
                ).all()
            )
        by_provider = {row.alipos_order_id: row for row in rows}
        for provider_id in stale_provider_ids[:-1]:
            assert by_provider[provider_id].alipos_status_check_attempted_at is not None
            assert by_provider[provider_id].alipos_status_checked_at is not None
            assert by_provider[provider_id].order_number == f"N-{str(provider_id)[-4:]}"
        assert (
            by_provider[failed_provider_id].alipos_status_check_attempted_at is not None
        )
        assert by_provider[failed_provider_id].alipos_status_checked_at is None
        assert (
            by_provider[fresh_provider_id].alipos_status_check_attempted_at == now_naive
        )
        hidden = [row for row in rows if row.table_id is None]
        unpaid = [row for row in rows if row.payment_method == "rahmat"]
        assert hidden[0].alipos_status_check_attempted_at is None
        assert unpaid[0].alipos_status_check_attempted_at is None
        reconcile_logs = [
            record.getMessage()
            for record in caplog.records
            if record.name == "uvicorn.error"
            and record.getMessage().startswith("staff_table_status_reconcile ")
        ]
        assert len(reconcile_logs) == 1
        assert "claimed=6 succeeded=5 failed=1" in reconcile_logs[0]
        assert all(
            str(provider_id) not in reconcile_logs[0]
            for provider_id in stale_provider_ids
        )
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin_engine.connect() as admin:
                await admin.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database AND pid <> pg_backend_pid()"
                    ),
                    {"database": test_database},
                )
                await admin.execute(text(f'DROP DATABASE IF EXISTS "{test_database}"'))
        finally:
            await admin_engine.dispose()
