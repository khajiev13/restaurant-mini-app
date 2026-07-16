import datetime
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import text

from app.config import settings
from app.middleware.telegram_auth import create_jwt
from app.models.models import Order, User


async def _table_order(db_session, *, paid: bool = False) -> tuple[User, Order]:
    telegram_id = 9_000_000_000 + uuid.uuid4().int % 1_000_000_000
    user = User(
        telegram_id=telegram_id,
        first_name="Table customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=telegram_id,
        items=[],
        delivery_info={"clientName": "Table customer", "phoneNumber": "+998900000000"},
        items_cost=36000,
        total_amount=39600,
        delivery_fee=0,
        payment_method="rahmat" if paid else "cash",
        payment_provider="multicard" if paid else None,
        payment_status="paid" if paid else None,
        multicard_payment_uuid="payment-uuid" if paid else None,
        discriminator="inplace",
        table_id=uuid.uuid4(),
        alipos_order_id=uuid.uuid4(),
        alipos_eats_id=f"cancel-{uuid.uuid4().hex}",
        alipos_sync_status="synced",
        status="NEW",
    )
    db_session.add_all([user, order])
    await db_session.commit()
    return user, order


async def _pending_online_table_order(db_session) -> tuple[User, Order]:
    telegram_id = 9_000_000_000 + uuid.uuid4().int % 1_000_000_000
    user = User(
        telegram_id=telegram_id,
        first_name="Table customer",
        last_name=None,
        username=None,
    )
    order = Order(
        user_id=telegram_id,
        items=[],
        delivery_info={"clientName": "Table customer", "phoneNumber": "+998900000000"},
        items_cost=36000,
        total_amount=39600,
        delivery_fee=0,
        payment_method="rahmat",
        payment_provider="multicard",
        payment_status="pending",
        payment_expires_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        + datetime.timedelta(minutes=10),
        multicard_invoice_uuid="invoice-uuid",
        multicard_checkout_url="https://pay.example/checkout",
        discriminator="inplace",
        table_id=uuid.uuid4(),
        alipos_eats_id=f"switch-{uuid.uuid4().hex}",
        alipos_sync_status="awaiting_payment",
        status="AWAITING_PAYMENT",
    )
    db_session.add_all([user, order])
    await db_session.commit()
    return user, order


async def _failed_online_table_order(db_session) -> tuple[User, Order]:
    user, order = await _pending_online_table_order(db_session)
    order.payment_status = "failed"
    order.payment_error = "Could not create the online payment"
    order.payment_expires_at = None
    order.multicard_invoice_uuid = None
    order.multicard_checkout_url = None
    order.status = "PAYMENT_FAILED"
    await db_session.commit()
    return user, order


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


@pytest.mark.asyncio
async def test_new_cash_table_order_can_be_cancelled(client, db_session):
    user, order = await _table_order(db_session)
    cancel = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel.assert_awaited_once_with(
        str(order.alipos_order_id),
        "Mijoz yangi buyurtmani bekor qildi",
    )
    assert order.status == "CANCELLED"
    assert response.json()["data"]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_accepted_table_order_cannot_be_cancelled(client, db_session):
    user, order = await _table_order(db_session)
    cancel = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "ACCEPTED_BY_RESTAURANT"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=cancel,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 409
    cancel.assert_not_awaited()
    assert order.status == "ACCEPTED_BY_RESTAURANT"


@pytest.mark.asyncio
async def test_paid_table_order_refunds_after_alipos_cancel(client, db_session):
    user, order = await _table_order(db_session, paid=True)
    refund = AsyncMock(return_value={"success": True})
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=refund,
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    refund.assert_awaited_once_with("payment-uuid")
    assert order.status == "CANCELLED"
    assert order.payment_status == "refunded"
    assert order.refund_sync_status == "refunded"
    assert response.json()["data"]["payment_status"] == "refunded"


@pytest.mark.asyncio
async def test_paid_table_order_keeps_refund_pending_when_outcome_is_unknown(
    client,
    db_session,
):
    user, order = await _table_order(db_session, paid=True)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.alipos_api.get_order_status",
            new=AsyncMock(return_value={"status": "NEW"}),
        ),
        patch(
            "app.services.order_service.alipos_api.cancel_order",
            new=AsyncMock(),
        ),
        patch(
            "app.services.order_service.multicard_api.refund_payment",
            new=AsyncMock(side_effect=httpx.ReadTimeout("outcome unknown")),
        ),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "CANCELLED"
    assert order.payment_status == "refund_pending"
    assert order.refund_sync_status == "unknown"
    assert response.json()["data"]["payment_status"] == "refund_pending"


@pytest.mark.asyncio
async def test_pending_online_table_order_can_switch_to_cash(client, db_session):
    user, order = await _pending_online_table_order(db_session)
    cancel_invoice = AsyncMock()
    submit = AsyncMock()
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=cancel_invoice,
        ),
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=submit,
        ),
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    submit.assert_awaited_once()
    assert order.payment_method == "cash"
    assert order.payment_provider is None
    assert order.payment_status is None
    assert order.multicard_checkout_url is None
    assert order.status == "NEW"
    assert order.alipos_sync_status == "sending"


@pytest.mark.asyncio
async def test_pending_online_table_order_cancels_invoice_before_local_order(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    cancel_invoice = AsyncMock()
    token = create_jwt(user.telegram_id)

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=cancel_invoice,
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_awaited_once_with("invoice-uuid")
    assert order.status == "CANCELLED"
    assert order.payment_status == "cancelled"


@pytest.mark.asyncio
async def test_pending_online_order_stays_payable_when_invoice_cancel_is_unknown(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with patch(
        "app.services.order_service.multicard_api.cancel_invoice_strict",
        new=AsyncMock(side_effect=RuntimeError("Multicard unavailable")),
    ):
        response = await client.delete(
            f"/api/orders/{order.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 502
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_status == "pending"


@pytest.mark.asyncio
async def test_switch_to_cash_keeps_online_order_when_invoice_cancel_is_unknown(
    client,
    db_session,
):
    user, order = await _pending_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=AsyncMock(side_effect=RuntimeError("Multicard unavailable")),
        ),
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=AsyncMock(),
        ) as submit,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 502
    submit.assert_not_awaited()
    assert order.payment_method == "rahmat"
    assert order.payment_status == "pending"
    assert order.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_failed_online_payment_can_create_a_fresh_checkout(
    client,
    db_session,
    monkeypatch,
):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", True)
    invoice = AsyncMock(return_value={
        "uuid": "new-invoice-uuid",
        "checkout_url": "https://pay.example/new-checkout",
    })

    with patch(
        "app.services.order_service.multicard_api.create_invoice",
        new=invoice,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/retry-payment",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_status == "pending"
    assert order.multicard_invoice_uuid == "new-invoice-uuid"
    assert response.json()["data"]["multicard_checkout_url"] == (
        "https://pay.example/new-checkout"
    )


@pytest.mark.asyncio
async def test_failed_online_payment_retry_is_blocked_after_capability_disabled(
    client,
    db_session,
    monkeypatch,
):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)
    monkeypatch.setattr(settings, "inplace_online_payment_enabled", False)
    monkeypatch.setattr(settings, "inplace_online_payment_test_telegram_ids", "")
    invoice = AsyncMock(
        return_value={
            "uuid": "unexpected-invoice-uuid",
            "checkout_url": "https://pay.example/unexpected-checkout",
        }
    )

    with patch(
        "app.services.order_service.multicard_api.create_invoice",
        new=invoice,
    ):
        response = await client.post(
            f"/api/orders/{order.id}/retry-payment",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Online payment is not available for table orders"
    )
    invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_online_payment_can_safely_switch_to_cash(client, db_session):
    user, order = await _failed_online_table_order(db_session)
    token = create_jwt(user.telegram_id)

    with (
        patch(
            "app.services.order_service.multicard_api.cancel_invoice_strict",
            new=AsyncMock(),
        ) as cancel_invoice,
        patch(
            "app.services.order_service.submit_order_to_alipos",
            new=AsyncMock(),
        ),
    ):
        response = await client.post(
            f"/api/orders/{order.id}/switch-to-cash",
            headers={"Authorization": f"Bearer {token}"},
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    cancel_invoice.assert_not_awaited()
    assert order.payment_method == "cash"
    assert order.payment_status is None
