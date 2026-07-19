from app.models.models import Order
from app.schemas.order import OrderResponse, OrderStatusResponse


def test_order_metadata_declares_one_active_delivery_per_staff_index():
    index = next(
        idx for idx in Order.__table__.indexes if idx.name == "uq_orders_one_active_delivery_per_staff"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["assigned_staff_id"]
    where_clause = str(index.dialect_options["postgresql"]["where"])

    assert "assigned_staff_id IS NOT NULL" in where_clause
    assert "delivered_at IS NULL" in where_clause
    assert "discriminator = 'delivery'" in where_clause


def test_order_contract_declares_table_pricing_and_sync_fields():
    expected_model_fields = {
        "table_id",
        "table_title",
        "hall_id",
        "hall_title",
        "service_percent",
        "table_access_expires_at",
        "items_cost",
        "alipos_sync_status",
        "alipos_sync_error",
        "cancel_requested_at",
    }

    assert expected_model_fields <= set(Order.__table__.columns.keys())
    assert {
        "table_title",
        "hall_title",
        "service_percent",
        "items_cost",
        "alipos_sync_status",
    } <= set(OrderResponse.model_fields)
    assert {
        "table_id",
        "hall_id",
        "alipos_order_id",
        "alipos_eats_id",
        "alipos_sync_error",
    }.isdisjoint(OrderResponse.model_fields)
    assert {
        "table_title",
        "hall_title",
        "service_percent",
        "alipos_sync_status",
    } <= set(OrderStatusResponse.model_fields)


def test_order_metadata_declares_customer_request_idempotency_index():
    index = next(
        idx for idx in Order.__table__.indexes if idx.name == "uq_orders_user_request"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == ["user_id", "client_request_id"]


def test_order_metadata_declares_staff_table_refresh_fields_and_index():
    assert {
        "invoice_cancel_status",
        "alipos_status_updated_at",
        "alipos_status_check_attempted_at",
        "alipos_status_checked_at",
    } <= set(Order.__table__.columns.keys())

    index = next(
        idx for idx in Order.__table__.indexes
        if idx.name == "idx_orders_inplace_workspace"
    )
    assert [column.name for column in index.columns] == [
        "table_id",
        "alipos_sync_status",
        "status",
        "alipos_status_check_attempted_at",
    ]
    assert "discriminator = 'inplace'" in str(
        index.dialect_options["postgresql"]["where"]
    )


def test_order_contact_phone_provenance_defaults_to_false():
    column = Order.__table__.columns["contact_phone_verified"]

    assert column.default.arg is False
    assert str(column.server_default.arg).lower() == "false"
