import datetime
import uuid
from decimal import Decimal

import pytest

from app.models.models import Order
from app.services.staff_table_service import (
    aggregate_order_items,
    build_staff_table_detail,
    build_staff_tables_overview,
    classify_table_order,
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
