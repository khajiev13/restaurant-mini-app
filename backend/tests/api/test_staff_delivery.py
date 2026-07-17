import asyncio
import datetime
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.main import app
from app.middleware.telegram_auth import create_jwt
from app.models.models import Address, Order, User
from app.services import staff_delivery_service

TAKE_ORDER_TIMEOUT_DETAIL = "Could not refresh order status. Try again."


@pytest_asyncio.fixture
async def staff_delivery_sessions(db_session):
    _ = db_session  # Ensure the shared test schema exists before opening connections.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    created_user_ids: list[int] = []

    async def override_get_db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as committing_client:
            yield committing_client, sessions, created_user_ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        if created_user_ids:
            async with sessions() as cleanup_db:
                await cleanup_db.execute(
                    delete(Order).where(Order.user_id.in_(created_user_ids))
                )
                await cleanup_db.execute(
                    delete(Address).where(Address.user_id.in_(created_user_ids))
                )
                await cleanup_db.execute(
                    delete(User).where(User.telegram_id.in_(created_user_ids))
                )
                await cleanup_db.commit()
        await engine.dispose()


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


async def _create_committed_take_order_case(
    sessions,
    created_user_ids: list[int],
    *,
    assigned_to_staff: bool = False,
) -> tuple[User, Order]:
    customer_id = 8_000_000_000 + uuid.uuid4().int % 400_000_000
    staff_id = 8_500_000_000 + uuid.uuid4().int % 400_000_000
    created_user_ids.extend([customer_id, staff_id])

    async with sessions() as setup_db:
        customer = await _create_user(setup_db, customer_id, "customer")
        staff = await _create_user(setup_db, staff_id, "staff")
        order = await _create_delivery_order(
            setup_db,
            customer,
            alipos_order_id=uuid.uuid4(),
            assigned_staff_id=staff_id if assigned_to_staff else None,
            assigned_at=(
                datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                if assigned_to_staff
                else None
            ),
            status_updated_at=(
                datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                - datetime.timedelta(minutes=1)
            ),
        )
    return staff, order


def _patch_take_order_deadlines(
    monkeypatch,
    *,
    provider_seconds: float,
    operation_seconds: float,
) -> None:
    monkeypatch.setattr(
        staff_delivery_service,
        "settings",
        SimpleNamespace(
            staff_take_order_provider_timeout_seconds=provider_seconds,
            staff_take_order_operation_timeout_seconds=operation_seconds,
        ),
        raising=False,
    )


async def _post_take_with_test_bound(
    client: AsyncClient,
    order_id: uuid.UUID,
    staff_id: int,
):
    try:
        return await asyncio.wait_for(
            client.post(
                f"/api/staff/orders/{order_id}/take",
                headers=_auth_headers(staff_id),
            ),
            timeout=0.5,
        )
    except TimeoutError:
        pytest.fail("take-order request exceeded its configured operation deadline")


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
async def test_staff_detail_hides_unassigned_orders_before_courier_stage(client, db_session):
    customer = await _create_user(db_session, 723, "customer")
    staff = await _create_user(db_session, 724, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        status="ACCEPTED_BY_RESTAURANT",
    )

    response = await client.get(
        f"/api/staff/orders/{order.id}",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_staff_detail_hides_unassigned_online_orders_until_paid(client, db_session):
    customer = await _create_user(db_session, 725, "customer")
    staff = await _create_user(db_session, 726, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        payment_method="rahmat",
        payment_status="pending",
    )

    response = await client.get(
        f"/api/staff/orders/{order.id}",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 404


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
async def test_take_order_provider_deadline_expires_without_assignment(
    staff_delivery_sessions,
    monkeypatch,
):
    client, sessions, created_user_ids = staff_delivery_sessions
    staff, order = await _create_committed_take_order_case(
        sessions,
        created_user_ids,
    )
    _patch_take_order_deadlines(
        monkeypatch,
        provider_seconds=0.02,
        operation_seconds=0.25,
    )
    provider_release = asyncio.Event()
    rollback_observed = asyncio.Event()
    original_rollback = AsyncSession.rollback

    async def track_rollback(session):
        rollback_observed.set()
        await original_rollback(session)

    async def never_complete(_order_id: str):
        await provider_release.wait()
        return {"status": "TAKEN_BY_COURIER"}

    monkeypatch.setattr(AsyncSession, "rollback", track_rollback)
    started_at = time.monotonic()
    try:
        with patch(
            "app.services.alipos_api.get_order_status",
            new=AsyncMock(side_effect=never_complete),
        ):
            response = await _post_take_with_test_bound(
                client,
                order.id,
                staff.telegram_id,
            )
    finally:
        provider_release.set()

    assert response.status_code == 503
    assert response.json()["detail"] == TAKE_ORDER_TIMEOUT_DETAIL
    assert time.monotonic() - started_at < 0.3
    assert rollback_observed.is_set()

    async with sessions() as verify_db:
        stored = await asyncio.wait_for(
            verify_db.scalar(
                select(Order).where(Order.id == order.id).with_for_update()
            ),
            timeout=0.2,
        )
        assert stored is not None
        assert stored.assigned_staff_id is None
        await verify_db.rollback()


@pytest.mark.asyncio
async def test_take_order_provider_read_happens_without_row_lock(
    staff_delivery_sessions,
    monkeypatch,
):
    client, sessions, created_user_ids = staff_delivery_sessions
    staff, order = await _create_committed_take_order_case(
        sessions,
        created_user_ids,
    )
    _patch_take_order_deadlines(
        monkeypatch,
        provider_seconds=0.5,
        operation_seconds=0.8,
    )
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def wait_during_provider_read(_order_id: str):
        provider_started.set()
        await release_provider.wait()
        return {"status": "TAKEN_BY_COURIER", "orderNumber": "A7-492"}

    with patch(
        "app.services.alipos_api.get_order_status",
        new=AsyncMock(side_effect=wait_during_provider_read),
    ):
        take_task = asyncio.create_task(
            client.post(
                f"/api/staff/orders/{order.id}/take",
                headers=_auth_headers(staff.telegram_id),
            )
        )
        try:
            await asyncio.wait_for(provider_started.wait(), timeout=0.2)
            try:
                async with sessions() as observer_db:
                    observed = await asyncio.wait_for(
                        observer_db.scalar(
                            select(Order).where(Order.id == order.id).with_for_update()
                        ),
                        timeout=0.2,
                    )
                    assert observed is not None
                    await observer_db.rollback()
            except TimeoutError:
                pytest.fail("provider status read held the order row lock")
            release_provider.set()
            response = await asyncio.wait_for(take_task, timeout=0.5)
        finally:
            release_provider.set()
            if not take_task.done():
                take_task.cancel()
            await asyncio.gather(take_task, return_exceptions=True)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_take_order_replay_by_same_staff_returns_active_order(
    staff_delivery_sessions,
    monkeypatch,
):
    client, sessions, created_user_ids = staff_delivery_sessions
    staff, order = await _create_committed_take_order_case(
        sessions,
        created_user_ids,
        assigned_to_staff=True,
    )
    _patch_take_order_deadlines(
        monkeypatch,
        provider_seconds=0.02,
        operation_seconds=0.1,
    )

    with patch(
        "app.services.alipos_api.get_order_status",
        new_callable=AsyncMock,
    ) as status_mock:
        response = await _post_take_with_test_bound(
            client,
            order.id,
            staff.telegram_id,
        )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(order.id)
    status_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_take_order_preserves_webhook_status_that_advances_between_provider_read_and_lock(
    staff_delivery_sessions,
    monkeypatch,
):
    client, sessions, created_user_ids = staff_delivery_sessions
    staff, order = await _create_committed_take_order_case(
        sessions,
        created_user_ids,
    )
    _patch_take_order_deadlines(
        monkeypatch,
        provider_seconds=0.5,
        operation_seconds=0.8,
    )
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()

    async def stale_provider_read(_order_id: str):
        provider_started.set()
        await release_provider.wait()
        return {"status": "TAKEN_BY_COURIER", "orderNumber": "A7-492"}

    with patch(
        "app.services.alipos_api.get_order_status",
        new=AsyncMock(side_effect=stale_provider_read),
    ):
        take_task = asyncio.create_task(
            client.post(
                f"/api/staff/orders/{order.id}/take",
                headers=_auth_headers(staff.telegram_id),
            )
        )
        try:
            await asyncio.wait_for(provider_started.wait(), timeout=0.2)
            try:
                async with sessions() as webhook_db:
                    await asyncio.wait_for(
                        webhook_db.execute(
                            update(Order)
                            .where(Order.id == order.id)
                            .values(
                                status="DELIVERED",
                                status_updated_at=datetime.datetime.now(datetime.UTC).replace(
                                    tzinfo=None
                                ),
                            )
                        ),
                        timeout=0.2,
                    )
                    await webhook_db.commit()
            except TimeoutError:
                pytest.fail("provider status read prevented the webhook update")
            release_provider.set()
            response = await asyncio.wait_for(take_task, timeout=0.5)
        finally:
            release_provider.set()
            if not take_task.done():
                take_task.cancel()
            await asyncio.gather(take_task, return_exceptions=True)

    assert response.status_code == 409
    assert response.json()["detail"] == "This order is no longer available."
    async with sessions() as verify_db:
        stored = await verify_db.get(Order, order.id)
        assert stored is not None
        assert stored.status == "DELIVERED"
        assert stored.assigned_staff_id is None


@pytest.mark.asyncio
async def test_take_order_operation_deadline_cancels_contended_lock_without_late_assignment(
    staff_delivery_sessions,
    monkeypatch,
):
    client, sessions, created_user_ids = staff_delivery_sessions
    staff, order = await _create_committed_take_order_case(
        sessions,
        created_user_ids,
    )
    _patch_take_order_deadlines(
        monkeypatch,
        provider_seconds=0.05,
        operation_seconds=0.15,
    )
    rollback_observed = asyncio.Event()
    original_rollback = AsyncSession.rollback

    async def track_rollback(session):
        rollback_observed.set()
        await original_rollback(session)

    monkeypatch.setattr(AsyncSession, "rollback", track_rollback)
    status_mock = AsyncMock(
        return_value={"status": "TAKEN_BY_COURIER", "orderNumber": "A7-492"}
    )

    async with sessions() as blocker_db:
        await blocker_db.execute(
            select(Order).where(Order.id == order.id).with_for_update()
        )
        with patch(
            "app.services.alipos_api.get_order_status",
            new=status_mock,
        ):
            response = await _post_take_with_test_bound(
                client,
                order.id,
                staff.telegram_id,
            )
        assert response.status_code == 503
        assert response.json()["detail"] == TAKE_ORDER_TIMEOUT_DETAIL
        assert rollback_observed.is_set()
        await blocker_db.rollback()

    await asyncio.sleep(0.05)
    async with sessions() as verify_db:
        stored = await asyncio.wait_for(
            verify_db.scalar(
                select(Order).where(Order.id == order.id).with_for_update()
            ),
            timeout=0.2,
        )
        assert stored is not None
        assert stored.assigned_staff_id is None
        await verify_db.rollback()


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
async def test_mark_delivered_repairs_missing_delivered_at(client, db_session):
    customer = await _create_user(db_session, 727, "customer")
    staff = await _create_user(db_session, 728, "staff")
    order = await _create_delivery_order(
        db_session,
        customer,
        assigned_staff_id=staff.telegram_id,
        status="DELIVERED",
        delivered_at=None,
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
