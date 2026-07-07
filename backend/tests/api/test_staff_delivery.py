import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import Address, Order, User


def _auth_headers(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(telegram_id)}"}


async def _create_user(db_session, telegram_id: int, role: str) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        username=f"user{telegram_id}",
        phone_number=f"+99890{telegram_id}",
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _create_delivery_order(db_session, user: User, **overrides) -> Order:
    address = Address(
        user_id=user.telegram_id,
        label="Home",
        full_address="Yakkasaray District, Shota Rustaveli 45",
        latitude="41.2995",
        longitude="69.2401",
    )
    db_session.add(address)
    await db_session.flush()

    order_data = {
        "user_id": user.telegram_id,
        "address_id": address.id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "name": "Somsa",
                "quantity": 2,
                "price": 18000,
                "modifications": [],
            }
        ],
        "total_amount": 36000,
        "delivery_fee": 0,
        "payment_method": "cash",
        "payment_status": None,
        "discriminator": "delivery",
        "status": "TAKEN_BY_COURIER",
        "order_number": "A7-492",
    }
    order_data.update(overrides)

    order = Order(
        **order_data,
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_customer_cannot_access_staff_available(client, db_session):
    customer = await _create_user(db_session, 701, "customer")

    response = await client.get(
        "/api/staff/orders/available",
        headers=_auth_headers(customer.telegram_id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_staff_can_list_available_orders(client, db_session):
    customer = await _create_user(db_session, 702, "customer")
    staff = await _create_user(db_session, 703, "staff")
    await _create_delivery_order(db_session, customer)

    response = await client.get(
        "/api/staff/orders/available",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["customer"]["telegram_id"] == customer.telegram_id
    assert data[0]["address"]["full_address"] == "Yakkasaray District, Shota Rustaveli 45"
    assert data[0]["payment_method"] == "cash"


@pytest.mark.asyncio
async def test_staff_can_take_available_order(client, db_session):
    customer = await _create_user(db_session, 704, "customer")
    staff = await _create_user(db_session, 705, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        alipos_order_id=uuid.uuid4(),
    )

    with patch(
        "app.services.alipos_api.get_order_status",
        new_callable=AsyncMock,
    ) as status_mock:
        status_mock.return_value = {
            "status": "TAKEN_BY_COURIER",
            "orderNumber": "A7-492",
        }
        response = await client.post(
            f"/api/staff/orders/{order.id}/take",
            headers=_auth_headers(staff.telegram_id),
        )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.assigned_staff_id == staff.telegram_id
    assert order.assigned_at is not None


@pytest.mark.asyncio
async def test_staff_cannot_take_second_active_order(client, db_session):
    customer = await _create_user(db_session, 706, "customer")
    staff = await _create_user(db_session, 707, "staff")
    await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=staff.telegram_id,
        assigned_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
    second_order = await _create_delivery_order(
        db_session,
        customer,
        order_number="B2-110",
    )

    response = await client.post(
        f"/api/staff/orders/{second_order.id}/take",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Finish your active delivery before taking another order."


@pytest.mark.asyncio
async def test_non_delivery_assignment_does_not_block_taking_delivery(client, db_session):
    customer = await _create_user(db_session, 715, "customer")
    staff = await _create_user(db_session, 716, "staff")
    await _create_delivery_order(
        db_session,
        customer,
        discriminator="pickup",
        assigned_staff_id=staff.telegram_id,
        assigned_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        order_number="P1-001",
    )
    delivery_order = await _create_delivery_order(
        db_session,
        customer,
        order_number="D1-001",
    )

    response = await client.post(
        f"/api/staff/orders/{delivery_order.id}/take",
        headers=_auth_headers(staff.telegram_id),
    )

    await db_session.refresh(delivery_order)
    assert response.status_code == 200
    assert delivery_order.assigned_staff_id == staff.telegram_id


@pytest.mark.asyncio
async def test_non_delivery_assignment_does_not_appear_as_active_delivery(client, db_session):
    customer = await _create_user(db_session, 717, "customer")
    staff = await _create_user(db_session, 718, "staff")
    await _create_delivery_order(
        db_session,
        customer,
        discriminator="pickup",
        assigned_staff_id=staff.telegram_id,
        assigned_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        order_number="P1-002",
    )

    response = await client.get(
        "/api/staff/orders/active",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 200
    assert response.json()["data"] is None


@pytest.mark.asyncio
async def test_only_assigned_staff_can_mark_delivered(client, db_session):
    customer = await _create_user(db_session, 708, "customer")
    assigned_staff = await _create_user(db_session, 709, "staff")
    other_staff = await _create_user(db_session, 710, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=assigned_staff.telegram_id,
    )

    response = await client.post(
        f"/api/staff/orders/{order.id}/delivered",
        headers=_auth_headers(other_staff.telegram_id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_staff_can_mark_delivered(client, db_session):
    customer = await _create_user(db_session, 711, "customer")
    staff = await _create_user(db_session, 712, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=staff.telegram_id,
    )

    response = await client.post(
        f"/api/staff/orders/{order.id}/delivered",
        headers=_auth_headers(staff.telegram_id),
    )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "DELIVERED"
    assert order.delivered_at is not None


@pytest.mark.asyncio
async def test_delivered_order_appears_in_completed(client, db_session):
    customer = await _create_user(db_session, 713, "customer")
    staff = await _create_user(db_session, 714, "staff")
    await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=staff.telegram_id,
        status="DELIVERED",
        delivered_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    response = await client.get(
        "/api/staff/orders/completed",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


@pytest.mark.asyncio
async def test_completed_endpoint_only_returns_delivery_orders(client, db_session):
    customer = await _create_user(db_session, 719, "customer")
    staff = await _create_user(db_session, 720, "staff")
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=staff.telegram_id,
        status="DELIVERED",
        delivered_at=now,
        order_number="D1-002",
    )
    await _create_delivery_order(
        db_session,
        customer,
        discriminator="pickup",
        assigned_staff_id=staff.telegram_id,
        status="DELIVERED",
        delivered_at=now,
        order_number="P1-003",
    )

    response = await client.get(
        "/api/staff/orders/completed",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 200
    assert [order["order_number"] for order in response.json()["data"]] == ["D1-002"]


@pytest.mark.asyncio
async def test_admin_can_access_staff_available_orders(client, db_session):
    customer = await _create_user(db_session, 721, "customer")
    admin = await _create_user(db_session, 722, "admin")
    await _create_delivery_order(db_session, customer, order_number="D1-003")

    response = await client.get(
        "/api/staff/orders/available",
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 200
    assert [order["order_number"] for order in response.json()["data"]] == ["D1-003"]
