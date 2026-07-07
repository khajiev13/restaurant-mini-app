from app.models.models import Order


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
