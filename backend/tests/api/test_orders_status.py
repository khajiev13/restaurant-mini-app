import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.middleware.telegram_auth import create_jwt
from app.models.models import Order, User


@pytest.mark.asyncio
async def test_order_status_poll_does_not_overwrite_local_delivered(client, db_session):
    user = User(
        telegram_id=6101,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=6101,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_order_id=uuid.uuid4(),
        status="DELIVERED",
        delivered_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
    db_session.add_all([user, order])
    await db_session.commit()

    token = create_jwt(user.telegram_id)
    with patch(
        "app.routers.orders.alipos_api.get_order_status",
        new=AsyncMock(return_value={"status": "TAKEN_BY_COURIER", "orderNumber": "99"}),
    ):
        response = await client.get(
            f"/api/orders/{order.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "DELIVERED"
    assert order.status == "DELIVERED"
    assert order.order_number is None


@pytest.mark.asyncio
async def test_order_status_poll_does_not_overwrite_delivery_that_wins_race(
    client,
    db_session,
):
    user = User(
        telegram_id=6102,
        first_name="Customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=6102,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_order_id=uuid.uuid4(),
        status="TAKEN_BY_COURIER",
    )
    db_session.add_all([user, order])
    await db_session.commit()

    async def deliver_before_alipos_returns(_alipos_order_id: str):
        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        await db_session.execute(
            text(
                "UPDATE orders "
                "SET status = 'DELIVERED', delivered_at = :now, status_updated_at = :now "
                "WHERE id = :order_id"
            ),
            {"now": now, "order_id": order.id},
        )
        await db_session.flush()
        return {"status": "READY", "orderNumber": "99"}

    token = create_jwt(user.telegram_id)
    with patch(
        "app.routers.orders.alipos_api.get_order_status",
        new=AsyncMock(side_effect=deliver_before_alipos_returns),
    ):
        response = await client.get(
            f"/api/orders/{order.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "DELIVERED"
    assert order.status == "DELIVERED"
    assert order.order_number is None
