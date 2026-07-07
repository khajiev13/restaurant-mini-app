# Staff Delivery Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 staff delivery: admins assign staff roles, staff can take exactly one ready delivery order, mark it delivered, and use a two-item staff UI.

**Architecture:** Add role and assignment fields to the existing SQLAlchemy models, then expose staff/admin APIs through thin routers backed by service modules. Add a focused staff frontend module that reuses the existing OLOT SOMSA design tokens instead of copying Stitch HTML.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL, Pydantic, pytest-asyncio, React 19, Vite, React Router, Vitest, Testing Library.

## Global Constraints

- Phase 1 only: one active delivery per staff member.
- No batch delivery or multiple stops.
- No route optimization.
- No separate courier app.
- No public registration for staff roles.
- Do not add `delivered_by_staff_id`.
- Delivery completion is local application state for this version.
- The assigned staff member is the delivery owner.
- The backend must enforce that only the assigned staff member can complete the order.
- The frontend must never be trusted for role.
- Every protected endpoint derives identity and role from the JWT and current database user.
- Use staff bottom nav items exactly: `Orders`, `Profile`.
- Use staff order tabs exactly: `Available`, `Active`, `Completed`.
- Available delivery order criteria: `discriminator = delivery`, `status = TAKEN_BY_COURIER`, `assigned_staff_id is null`, and payment is cash or paid.
- Missing phone/address/map states are out of scope because customer phone, delivery address, items, total, and payment method are already validated before the order enters this workflow.
- Keep CTAs visually consistent with existing gradient primary buttons.
- Do not hide `Take Order`, `Open Map`, `Call Customer`, or `Mark Delivered` below unclear scroll depth.

---

## File Structure

Backend files:

- Modify `backend/app/config.py`: add `bootstrap_admin_telegram_ids` and a parsed `bootstrap_admin_ids` property.
- Modify `backend/app/models/models.py`: add user role, order assignment columns, explicit relationships, and indexes.
- Modify `database/init.sql`: add role and assignment columns plus indexes for fresh/existing databases.
- Create `database/migrations/2026-07-07-staff-delivery-phase-1.sql`: production migration for existing PostgreSQL databases.
- Modify `backend/app/schemas/user.py`: expose role and add admin role update schema.
- Modify `backend/app/schemas/order.py`: add staff order response schemas.
- Create `backend/app/services/permissions.py`: role constants and authorization helpers.
- Create `backend/app/services/order_status_service.py`: terminal-safe status update helper.
- Create `backend/app/services/staff_delivery_service.py`: staff list/take/delivered business rules.
- Create `backend/app/services/admin_user_service.py`: admin user search and role updates.
- Create `backend/app/routers/staff.py`: staff delivery endpoints.
- Create `backend/app/routers/admin.py`: admin role endpoints.
- Modify `backend/app/routers/auth.py`: bootstrap admin role during Telegram auth.
- Modify `backend/app/routers/orders.py`: use status helper when polling AliPOS status.
- Modify `backend/app/routers/webhooks.py`: use status helper for AliPOS status webhooks.
- Modify `backend/app/main.py`: include staff/admin routers.
- Create `backend/tests/api/test_staff_delivery.py`: staff flow tests.
- Create `backend/tests/api/test_admin_users.py`: role management tests.
- Modify `backend/tests/api/test_auth.py`: bootstrap admin role test.

Frontend files:

- Modify `frontend/src/types/api.ts`: add `role` to `User`.
- Create `frontend/src/types/staff.ts`: staff order response types.
- Modify `frontend/src/services/api.ts`: add admin role APIs or export shared `api`.
- Create `frontend/src/services/staffApi.ts`: staff delivery API functions.
- Modify `frontend/src/stores/authStore.ts`: store the current user role after auth.
- Modify `frontend/src/App.tsx`: role-aware routes and staff routes.
- Create `frontend/src/components/staff/StaffLayout.tsx`: staff top bar and two-item bottom nav.
- Create `frontend/src/components/staff/StaffOrderTabs.tsx`: segmented tabs.
- Create `frontend/src/components/staff/StaffOrderCard.tsx`: available/completed card.
- Create `frontend/src/components/staff/StaffPaymentBlock.tsx`: cash/paid block.
- Create `frontend/src/components/staff/ConfirmDeliveredSheet.tsx`: delivered confirmation sheet.
- Create `frontend/src/pages/staff/StaffOrdersPage.tsx`: available/active/completed tabs.
- Create `frontend/src/pages/staff/StaffOrderDetailPage.tsx`: pre-take detail and take action.
- Create `frontend/src/pages/staff/StaffProfilePage.tsx`: staff profile with staff nav.
- Create `frontend/src/pages/staff/StaffOrdersPage.test.tsx`: staff UI tests.
- Modify `frontend/src/App.test.tsx`: role-aware routing tests.
- Modify `frontend/src/mocks/handlers.ts`: staff API mocks if tests use MSW for these endpoints.

---

### Task 1: Backend Role And Assignment Data Model

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `database/init.sql`
- Create: `database/migrations/2026-07-07-staff-delivery-phase-1.sql`
- Test: `backend/tests/api/test_auth.py`

**Interfaces:**
- Produces: `User.role: str`
- Produces: `Order.assigned_staff_id: int | None`
- Produces: `Order.assigned_at: datetime | None`
- Produces: `Order.delivered_at: datetime | None`
- Produces: `settings.bootstrap_admin_ids: set[int]`
- Consumed by: Tasks 2, 3, 4, 5, 6

- [ ] **Step 1: Write failing auth bootstrap test**

Add this test to `backend/tests/api/test_auth.py`.

```python
@pytest.mark.asyncio
async def test_auth_bootstraps_configured_admin(client, monkeypatch):
    fake_user = {
        "id": 424242,
        "first_name": "Admin",
        "last_name": "User",
        "username": "adminuser",
    }
    monkeypatch.setattr("app.config.settings.bootstrap_admin_telegram_ids", "424242")

    with patch("app.routers.auth.validate_init_data", return_value=fake_user):
        auth_response = await client.post("/api/auth/telegram", json={"init_data": "mocked"})

    token = auth_response.json()["data"]["access_token"]
    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert auth_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["data"]["role"] == "admin"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_auth.py::test_auth_bootstraps_configured_admin -v
```

Expected: FAIL because `role` and `bootstrap_admin_telegram_ids` do not exist.

- [ ] **Step 3: Add bootstrap admin config**

In `backend/app/config.py`, add this field near the Telegram settings:

```python
    bootstrap_admin_telegram_ids: str = ""
```

Add this property inside `Settings`:

```python
    @property
    def bootstrap_admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for raw_id in _split_csv(self.bootstrap_admin_telegram_ids):
            try:
                ids.add(int(raw_id))
            except ValueError:
                continue
        return ids
```

- [ ] **Step 4: Add ORM fields and relationships**

In `backend/app/models/models.py`, update imports:

```python
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Numeric, String, Text
```

Add `role` to `User`:

```python
    role: Mapped[str] = mapped_column(String(32), default="customer")
```

Update `User.orders` and add `assigned_orders`:

```python
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Order.user_id",
    )
    assigned_orders: Mapped[list["Order"]] = relationship(
        back_populates="assigned_staff",
        foreign_keys="Order.assigned_staff_id",
    )
```

Add assignment fields to `Order` after `address_id`:

```python
    assigned_staff_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
    )
    assigned_at: Mapped[datetime.datetime | None] = mapped_column()
    delivered_at: Mapped[datetime.datetime | None] = mapped_column()
```

Update `Order.user` and add `assigned_staff` and `address`:

```python
    user: Mapped["User"] = relationship(
        back_populates="orders",
        foreign_keys=[user_id],
    )
    assigned_staff: Mapped["User | None"] = relationship(
        back_populates="assigned_orders",
        foreign_keys=[assigned_staff_id],
    )
    address: Mapped["Address | None"] = relationship()
```

Update `Order.__table_args__` by adding:

```python
        Index("idx_orders_assigned_staff_id", "assigned_staff_id"),
        Index("idx_orders_delivered_at", "delivered_at"),
        Index("idx_orders_staff_available", "status", "assigned_staff_id", "discriminator"),
```

Add this to `User.__table_args__` after the relationships:

```python
    __table_args__ = (
        CheckConstraint("role IN ('customer', 'staff', 'admin')", name="ck_users_role_valid"),
    )
```

- [ ] **Step 5: Update user schema and auth bootstrap**

In `backend/app/schemas/user.py`, add `role` to `UserResponse`:

```python
    role: str = "customer"
```

In `backend/app/routers/auth.py`, after loading or creating `user`, add:

```python
    if telegram_id in settings.bootstrap_admin_ids:
        user.role = "admin"
```

- [ ] **Step 6: Update database SQL files**

In `database/init.sql`, add `role` to the `users` table:

```sql
    role         VARCHAR(32) NOT NULL DEFAULT 'customer',
```

Add assignment columns to the `orders` table after `address_id`:

```sql
    assigned_staff_id     BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    assigned_at           TIMESTAMP,
    delivered_at          TIMESTAMP,
```

Add migration SQL at the bottom of `database/init.sql`:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'customer';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_staff_id BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_users_role_valid'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT ck_users_role_valid
            CHECK (role IN ('customer', 'staff', 'admin'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_orders_assigned_staff_id ON orders(assigned_staff_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_staff_available ON orders(status, assigned_staff_id, discriminator);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_one_active_delivery_per_staff
  ON orders(assigned_staff_id)
  WHERE assigned_staff_id IS NOT NULL
    AND delivered_at IS NULL
    AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED');
```

Create `database/migrations/2026-07-07-staff-delivery-phase-1.sql` with the same migration block from this step.

- [ ] **Step 7: Run backend tests**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_auth.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/app/config.py backend/app/models/models.py backend/app/schemas/user.py backend/app/routers/auth.py backend/tests/api/test_auth.py database/init.sql database/migrations/2026-07-07-staff-delivery-phase-1.sql
git commit -m "feat: add staff role and delivery assignment fields"
```

---

### Task 2: Backend Permissions And Status Guardrails

**Files:**
- Create: `backend/app/services/permissions.py`
- Create: `backend/app/services/order_status_service.py`
- Modify: `backend/app/routers/orders.py`
- Modify: `backend/app/routers/webhooks.py`
- Test: `backend/tests/api/test_webhooks.py`

**Interfaces:**
- Consumes: `User.role`
- Produces: `require_role(user: User, allowed_roles: set[str]) -> None`
- Produces: `is_staff_role(user: User) -> bool`
- Produces: `apply_alipos_status_update(order: Order, status_value: str, order_number: str | None) -> bool`
- Consumed by: Tasks 3 and 4

- [ ] **Step 1: Write failing terminal-status webhook test**

Add this test to `backend/tests/api/test_webhooks.py`.

```python
@pytest.mark.asyncio
async def test_order_status_webhook_does_not_overwrite_local_delivered(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "alipos_api_client_id", "client")
    monkeypatch.setattr(settings, "alipos_api_client_secret", "secret")

    user = User(telegram_id=5001, first_name="Customer", last_name=None, username=None)
    order = Order(
        user_id=5001,
        items=[],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        discriminator="delivery",
        alipos_eats_id="eats-delivered",
        status="DELIVERED",
        delivered_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
    db_session.add_all([user, order])
    await db_session.commit()

    response = await client.post(
        "/api/webhooks/order-status",
        json={"eatsId": "eats-delivered", "status": "TAKEN_BY_COURIER", "orderNumber": "99"},
        headers={"clientId": "client", "clientSecret": "secret"},
    )

    await db_session.refresh(order)
    assert response.status_code == 200
    assert order.status == "DELIVERED"
    assert order.order_number is None
```

Also add these imports at the top of `backend/tests/api/test_webhooks.py`:

```python
import datetime
from app.models.models import Order, User
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_webhooks.py::test_order_status_webhook_does_not_overwrite_local_delivered -v
```

Expected: FAIL because the webhook writes `order.status` directly.

- [ ] **Step 3: Add permission helpers**

Create `backend/app/services/permissions.py`:

```python
from fastapi import HTTPException, status

from app.models.models import User

ROLE_CUSTOMER = "customer"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
STAFF_ROLES = {ROLE_STAFF, ROLE_ADMIN}


def require_role(user: User, allowed_roles: set[str]) -> None:
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


def require_staff(user: User) -> None:
    require_role(user, STAFF_ROLES)


def require_admin(user: User) -> None:
    require_role(user, {ROLE_ADMIN})


def is_admin(user: User) -> bool:
    return user.role == ROLE_ADMIN
```

- [ ] **Step 4: Add terminal-safe status helper**

Create `backend/app/services/order_status_service.py`:

```python
import datetime

from app.models.models import Order

TERMINAL_LOCAL_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}


def normalize_order_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "CANCELED":
        return "CANCELLED"
    return normalized


def apply_alipos_status_update(
    order: Order,
    status_value: str,
    order_number: str | None = None,
) -> bool:
    if order.status in TERMINAL_LOCAL_STATUSES:
        return False

    next_status = normalize_order_status(status_value)
    changed = False

    if order.status != next_status:
        order.status = next_status
        changed = True

    if order_number and order.order_number != order_number:
        order.order_number = order_number
        changed = True

    if changed:
        order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    return changed
```

- [ ] **Step 5: Use status helper in webhook and polling**

In `backend/app/routers/webhooks.py`, import:

```python
from app.services.order_status_service import apply_alipos_status_update
```

Replace direct status assignment in `order_status_webhook`:

```python
        if order and apply_alipos_status_update(order, new_status, order_number):
            await db.commit()
```

In `backend/app/routers/orders.py`, import:

```python
from app.services.order_status_service import apply_alipos_status_update
```

Replace the direct status update inside `get_order_status`:

```python
            new_status = alipos_data.get("status", order.status)
            order_number = alipos_data.get("orderNumber")
            if apply_alipos_status_update(order, new_status, order_number):
                await db.commit()
```

- [ ] **Step 6: Run webhook and order tests**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_webhooks.py tests/api/test_auth.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/app/services/permissions.py backend/app/services/order_status_service.py backend/app/routers/orders.py backend/app/routers/webhooks.py backend/tests/api/test_webhooks.py
git commit -m "feat: protect local terminal delivery statuses"
```

---

### Task 3: Staff Delivery Backend API

**Files:**
- Modify: `backend/app/schemas/order.py`
- Create: `backend/app/services/staff_delivery_service.py`
- Create: `backend/app/routers/staff.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_staff_delivery.py`

**Interfaces:**
- Consumes: `require_staff(user: User) -> None`
- Consumes: `apply_alipos_status_update(order: Order, status_value: str, order_number: str | None) -> bool`
- Produces: `StaffOrderResponse`
- Produces: `list_available_orders(db: AsyncSession) -> list[Order]`
- Produces: `get_active_order(db: AsyncSession, staff: User) -> Order | None`
- Produces: `take_order(db: AsyncSession, staff: User, order_id: uuid.UUID) -> Order`
- Produces: `mark_order_delivered(db: AsyncSession, staff: User, order_id: uuid.UUID) -> Order`
- Produces endpoints under `/api/staff/orders`
- Consumed by: Frontend Tasks 5 and 6

- [ ] **Step 1: Write failing staff API tests**

Create `backend/tests/api/test_staff_delivery.py`:

```python
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

    order = Order(
        user_id=user.telegram_id,
        address_id=address.id,
        items=[{"id": "item-1", "name": "Somsa", "quantity": 2, "price": 18000, "modifications": []}],
        total_amount=36000,
        delivery_fee=0,
        payment_method="cash",
        payment_status=None,
        discriminator="delivery",
        status="TAKEN_BY_COURIER",
        order_number="A7-492",
        **overrides,
    )
    db_session.add(order)
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_customer_cannot_access_staff_available(client, db_session):
    customer = await _create_user(db_session, 701, "customer")

    response = await client.get("/api/staff/orders/available", headers=_auth_headers(customer.telegram_id))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_staff_can_list_available_orders(client, db_session):
    customer = await _create_user(db_session, 702, "customer")
    staff = await _create_user(db_session, 703, "staff")
    await _create_delivery_order(db_session, customer)

    response = await client.get("/api/staff/orders/available", headers=_auth_headers(staff.telegram_id))

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
    order = await _create_delivery_order(db_session, customer)

    with patch("app.services.staff_delivery_service.alipos_api.get_order_status", new_callable=AsyncMock) as status_mock:
        status_mock.return_value = {"status": "TAKEN_BY_COURIER", "orderNumber": "A7-492"}
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
    active_order = await _create_delivery_order(db_session, customer, assigned_staff_id=staff.telegram_id)
    active_order.assigned_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    second_order = await _create_delivery_order(db_session, customer, order_number="B2-110")
    await db_session.commit()

    response = await client.post(
        f"/api/staff/orders/{second_order.id}/take",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Finish your active delivery before taking another order."


@pytest.mark.asyncio
async def test_only_assigned_staff_can_mark_delivered(client, db_session):
    customer = await _create_user(db_session, 708, "customer")
    assigned_staff = await _create_user(db_session, 709, "staff")
    other_staff = await _create_user(db_session, 710, "staff")
    order = await _create_delivery_order(db_session, customer, assigned_staff_id=assigned_staff.telegram_id)

    response = await client.post(
        f"/api/staff/orders/{order.id}/delivered",
        headers=_auth_headers(other_staff.telegram_id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assigned_staff_can_mark_delivered(client, db_session):
    customer = await _create_user(db_session, 711, "customer")
    staff = await _create_user(db_session, 712, "staff")
    order = await _create_delivery_order(db_session, customer, assigned_staff_id=staff.telegram_id)

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

    response = await client.get("/api/staff/orders/completed", headers=_auth_headers(staff.telegram_id))

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_staff_delivery.py -v
```

Expected: FAIL because `/api/staff/orders/*` routes do not exist.

- [ ] **Step 3: Add staff schemas**

Append to `backend/app/schemas/order.py`:

```python
class StaffCustomerResponse(BaseModel):
    telegram_id: int
    first_name: str
    last_name: str | None = None
    phone_number: str | None = None


class StaffAddressResponse(BaseModel):
    full_address: str
    latitude: str | None = None
    longitude: str | None = None
    entrance: str | None = None
    apartment: str | None = None
    floor: str | None = None
    courier_instructions: str | None = None


class StaffSummaryResponse(BaseModel):
    telegram_id: int
    first_name: str
    last_name: str | None = None


class StaffOrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str | None = None
    status: str
    created_at: datetime.datetime
    status_updated_at: datetime.datetime | None = None
    assigned_at: datetime.datetime | None = None
    delivered_at: datetime.datetime | None = None
    customer: StaffCustomerResponse
    address: StaffAddressResponse
    items: list[dict]
    total_amount: float
    delivery_fee: float
    payment_method: str
    payment_status: str | None = None
    assigned_staff: StaffSummaryResponse | None = None


def build_staff_order_response(order) -> StaffOrderResponse:
    address = order.address
    assigned_staff = order.assigned_staff
    return StaffOrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        created_at=order.created_at,
        status_updated_at=order.status_updated_at,
        assigned_at=order.assigned_at,
        delivered_at=order.delivered_at,
        customer=StaffCustomerResponse(
            telegram_id=order.user.telegram_id,
            first_name=order.user.first_name,
            last_name=order.user.last_name,
            phone_number=order.user.phone_number,
        ),
        address=StaffAddressResponse(
            full_address=address.full_address if address else "",
            latitude=address.latitude if address else None,
            longitude=address.longitude if address else None,
            entrance=address.entrance if address else None,
            apartment=address.apartment if address else None,
            floor=address.floor if address else None,
            courier_instructions=address.courier_instructions if address else None,
        ),
        items=order.items,
        total_amount=float(order.total_amount),
        delivery_fee=float(order.delivery_fee),
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        assigned_staff=(
            StaffSummaryResponse(
                telegram_id=assigned_staff.telegram_id,
                first_name=assigned_staff.first_name,
                last_name=assigned_staff.last_name,
            )
            if assigned_staff
            else None
        ),
    )
```

- [ ] **Step 4: Add staff delivery service**

Create `backend/app/services/staff_delivery_service.py`:

```python
import datetime
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Order, User
from app.services import alipos_api
from app.services.order_status_service import apply_alipos_status_update
from app.services.permissions import require_staff

AVAILABLE_STATUS = "TAKEN_BY_COURIER"
TERMINAL_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}


def _staff_order_options():
    return (
        selectinload(Order.user),
        selectinload(Order.address),
        selectinload(Order.assigned_staff),
    )


def _is_collectible_or_settled(order: Order) -> bool:
    return order.payment_method == "cash" or order.payment_status == "paid"


def _active_order_filter(staff_id: int):
    return (
        Order.assigned_staff_id == staff_id,
        Order.delivered_at.is_(None),
        Order.status.not_in(TERMINAL_STATUSES),
    )


async def list_available_orders(db: AsyncSession, current_user: User) -> list[Order]:
    require_staff(current_user)
    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(
            Order.discriminator == "delivery",
            Order.status == AVAILABLE_STATUS,
            Order.assigned_staff_id.is_(None),
            or_(Order.payment_method == "cash", Order.payment_status == "paid"),
        )
        .order_by(Order.created_at.asc())
    )
    return list(result.scalars().all())


async def get_active_order(db: AsyncSession, current_user: User) -> Order | None:
    require_staff(current_user)
    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(*_active_order_filter(current_user.telegram_id))
        .order_by(Order.assigned_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_completed_orders(db: AsyncSession, current_user: User) -> list[Order]:
    require_staff(current_user)
    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(
            Order.assigned_staff_id == current_user.telegram_id,
            Order.status == "DELIVERED",
            Order.delivered_at.is_not(None),
        )
        .order_by(Order.delivered_at.desc())
    )
    return list(result.scalars().all())


async def get_staff_order(db: AsyncSession, current_user: User, order_id: uuid.UUID) -> Order:
    require_staff(current_user)
    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(Order.id == order_id, Order.discriminator == "delivery")
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.assigned_staff_id not in (None, current_user.telegram_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Order is assigned to another staff member")
    return order


async def _ensure_no_active_order(db: AsyncSession, staff_id: int) -> None:
    result = await db.execute(select(Order.id).where(*_active_order_filter(staff_id)).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish your active delivery before taking another order.",
        )


async def take_order(db: AsyncSession, current_user: User, order_id: uuid.UUID) -> Order:
    require_staff(current_user)
    await _ensure_no_active_order(db, current_user.telegram_id)

    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(Order.id == order_id, Order.discriminator == "delivery")
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.assigned_staff_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order was already taken by another staff member.")

    if order.alipos_order_id:
        try:
            alipos_data = await alipos_api.get_order_status(str(order.alipos_order_id))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not refresh order status. Try again.") from exc
        apply_alipos_status_update(order, alipos_data.get("status", order.status), alipos_data.get("orderNumber"))

    if order.status != AVAILABLE_STATUS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order is no longer available.")

    if not _is_collectible_or_settled(order):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order is not ready for delivery payment handling.")

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.assigned_staff_id = current_user.telegram_id
    order.assigned_at = now
    await db.commit()
    await db.refresh(order, attribute_names=["user", "address", "assigned_staff"])
    return order


async def mark_order_delivered(db: AsyncSession, current_user: User, order_id: uuid.UUID) -> Order:
    require_staff(current_user)
    result = await db.execute(
        select(Order)
        .options(*_staff_order_options())
        .where(Order.id == order_id, Order.discriminator == "delivery")
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.assigned_staff_id != current_user.telegram_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned staff member can complete this order.")

    if order.status in {"CANCELLED", "CANCELED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order was cancelled.")

    if order.status == "DELIVERED":
        return order

    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    order.status = "DELIVERED"
    order.delivered_at = now
    order.status_updated_at = now
    await db.commit()
    await db.refresh(order, attribute_names=["user", "address", "assigned_staff"])
    return order
```

- [ ] **Step 5: Add staff router and include it**

Create `backend/app/routers/staff.py`:

```python
import uuid

from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.order import build_staff_order_response
from app.services import staff_delivery_service

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/orders/available")
async def available_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_available_orders(db, current_user)
    return ApiResponse(success=True, data=[build_staff_order_response(order).model_dump(mode="json") for order in orders])


@router.get("/orders/active")
async def active_order(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.get_active_order(db, current_user)
    return ApiResponse(success=True, data=build_staff_order_response(order).model_dump(mode="json") if order else None)


@router.get("/orders/completed")
async def completed_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_completed_orders(db, current_user)
    return ApiResponse(success=True, data=[build_staff_order_response(order).model_dump(mode="json") for order in orders])


@router.get("/orders/{order_id}")
async def get_staff_order(order_id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.get_staff_order(db, current_user, order_id)
    return ApiResponse(success=True, data=build_staff_order_response(order).model_dump(mode="json"))


@router.post("/orders/{order_id}/take")
async def take_order(order_id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.take_order(db, current_user, order_id)
    return ApiResponse(success=True, data=build_staff_order_response(order).model_dump(mode="json"))


@router.post("/orders/{order_id}/delivered")
async def mark_delivered(order_id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.mark_order_delivered(db, current_user, order_id)
    return ApiResponse(success=True, data=build_staff_order_response(order).model_dump(mode="json"))
```

In `backend/app/main.py`, update imports:

```python
from app.routers import addresses, auth, geocoding, menu, orders, staff, users, webhooks
```

Add router include:

```python
app.include_router(staff.router, prefix="/api")
```

- [ ] **Step 6: Run staff tests**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_staff_delivery.py -v
```

Expected: PASS.

- [ ] **Step 7: Run all backend tests**

Run:

```bash
cd backend
source .venv/bin/activate
pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/app/schemas/order.py backend/app/services/staff_delivery_service.py backend/app/routers/staff.py backend/app/main.py backend/tests/api/test_staff_delivery.py
git commit -m "feat: add staff delivery order endpoints"
```

---

### Task 4: Admin Role Management Backend API

**Files:**
- Modify: `backend/app/schemas/user.py`
- Create: `backend/app/services/admin_user_service.py`
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/api/test_admin_users.py`

**Interfaces:**
- Consumes: `require_admin(user: User) -> None`
- Produces endpoints under `/api/admin/users`
- Produces: `UserRoleUpdate(role: str)`
- Consumed by: admin dashboard and frontend API client

- [ ] **Step 1: Write failing admin tests**

Create `backend/tests/api/test_admin_users.py`:

```python
from app.middleware.telegram_auth import create_jwt
from app.models.models import User

import pytest


def _auth_headers(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(telegram_id)}"}


async def _user(db_session, telegram_id: int, role: str, phone: str | None = None) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        username=f"user{telegram_id}",
        phone_number=phone,
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_non_admin_cannot_search_users(client, db_session):
    staff = await _user(db_session, 801, "staff")

    response = await client.get("/api/admin/users?query=user", headers=_auth_headers(staff.telegram_id))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_search_users_by_phone(client, db_session):
    admin = await _user(db_session, 802, "admin")
    target = await _user(db_session, 803, "customer", phone="+998901112233")

    response = await client.get("/api/admin/users?query=1112233", headers=_auth_headers(admin.telegram_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["telegram_id"] == target.telegram_id


@pytest.mark.asyncio
async def test_admin_can_assign_staff_role(client, db_session):
    admin = await _user(db_session, 804, "admin")
    target = await _user(db_session, 805, "customer")

    response = await client.patch(
        f"/api/admin/users/{target.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(admin.telegram_id),
    )

    await db_session.refresh(target)
    assert response.status_code == 200
    assert target.role == "staff"
    assert response.json()["data"]["role"] == "staff"


@pytest.mark.asyncio
async def test_final_admin_cannot_remove_own_admin_role(client, db_session):
    admin = await _user(db_session, 806, "admin")

    response = await client.patch(
        f"/api/admin/users/{admin.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_admin_users.py -v
```

Expected: FAIL because `/api/admin/users` routes do not exist.

- [ ] **Step 3: Add user role update schema**

In `backend/app/schemas/user.py`, append:

```python
class UserRoleUpdate(BaseModel):
    role: str
```

- [ ] **Step 4: Add admin user service**

Create `backend/app/services/admin_user_service.py`:

```python
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.permissions import ROLE_ADMIN, require_admin

VALID_ROLES = {"customer", "staff", "admin"}


async def search_users(db: AsyncSession, current_user: User, query: str) -> list[User]:
    require_admin(current_user)
    normalized = query.strip()
    statement = select(User).order_by(User.created_at.desc()).limit(25)
    if normalized:
        pattern = f"%{normalized}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.username.ilike(pattern),
                User.phone_number.ilike(pattern),
            )
        )
    result = await db.execute(statement)
    return list(result.scalars().all())


async def update_user_role(
    db: AsyncSession,
    current_user: User,
    telegram_id: int,
    role: str,
) -> User:
    require_admin(current_user)
    if role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role")

    result = await db.execute(select(User).where(User.telegram_id == telegram_id).with_for_update())
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target.telegram_id == current_user.telegram_id and target.role == ROLE_ADMIN and role != ROLE_ADMIN:
        count_result = await db.execute(select(func.count()).select_from(User).where(User.role == ROLE_ADMIN))
        if int(count_result.scalar() or 0) <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove the final admin role.")

    target.role = role
    await db.commit()
    await db.refresh(target)
    return target
```

- [ ] **Step 5: Add admin router and include it**

Create `backend/app/routers/admin.py`:

```python
from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse, UserRoleUpdate
from app.services import admin_user_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def search_users(query: str = "", current_user: CurrentUserDep = None, db: DbDep = None) -> ApiResponse:
    users = await admin_user_service.search_users(db, current_user, query)
    return ApiResponse(success=True, data=[UserResponse.model_validate(user).model_dump() for user in users])


@router.patch("/users/{telegram_id}/role")
async def update_user_role(
    telegram_id: int,
    body: UserRoleUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    user = await admin_user_service.update_user_role(db, current_user, telegram_id, body.role)
    return ApiResponse(success=True, data=UserResponse.model_validate(user).model_dump())
```

In `backend/app/main.py`, update imports:

```python
from app.routers import addresses, admin, auth, geocoding, menu, orders, staff, users, webhooks
```

Add:

```python
app.include_router(admin.router, prefix="/api")
```

- [ ] **Step 6: Run admin tests**

Run:

```bash
cd backend
source .venv/bin/activate
pytest tests/api/test_admin_users.py -v
```

Expected: PASS.

- [ ] **Step 7: Run backend test suite**

Run:

```bash
cd backend
source .venv/bin/activate
pytest -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/app/schemas/user.py backend/app/services/admin_user_service.py backend/app/routers/admin.py backend/app/main.py backend/tests/api/test_admin_users.py
git commit -m "feat: add admin user role endpoints"
```

---

### Task 5: Frontend Auth, Types, And Staff Routing

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/types/staff.ts`
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/services/staffApi.ts`
- Modify: `frontend/src/stores/authStore.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/staff/StaffOrdersPage.tsx` with temporary route shell
- Create: `frontend/src/pages/staff/StaffOrderDetailPage.tsx` with temporary route shell
- Create: `frontend/src/pages/staff/StaffProfilePage.tsx` with temporary route shell
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: backend `User.role`
- Produces: `StaffOrder` TypeScript type
- Produces: `getAvailableStaffOrders()`, `getActiveStaffOrder()`, `getCompletedStaffOrders()`, `getStaffOrder(id)`, `takeStaffOrder(id)`, `markStaffOrderDelivered(id)`
- Produces: role-aware `/staff/orders`, `/staff/orders/:orderId`, `/profile`
- Consumed by: Task 6

- [ ] **Step 1: Write failing app route test**

Update `frontend/src/App.test.tsx` auth mock:

```tsx
const authState = vi.hoisted(() => ({
  authenticate: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  user: null as { role: string } | null,
  isLoading: false,
}));
```

Add mocks:

```tsx
vi.mock('./pages/staff/StaffOrdersPage', () => ({
  default: () => <div>Staff orders page</div>,
}));

vi.mock('./pages/staff/StaffOrderDetailPage', () => ({
  default: () => <div>Staff order detail page</div>,
}));

vi.mock('./pages/staff/StaffProfilePage', () => ({
  default: () => <div>Staff profile page</div>,
}));
```

Add test:

```tsx
it('routes staff users from home to staff orders', () => {
  authState.user = { role: 'staff' };

  const view = render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Staff orders page')).toBeInTheDocument();
});
```

In `beforeEach`, reset:

```tsx
    authState.user = null;
    authState.isLoading = false;
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/App.test.tsx
```

Expected: FAIL because staff routes and user role state do not exist.

- [ ] **Step 3: Add frontend role and staff types**

In `frontend/src/types/api.ts`, update `User`:

```ts
  role: 'customer' | 'staff' | 'admin';
```

Create `frontend/src/types/staff.ts`:

```ts
export interface StaffCustomer {
  telegram_id: number;
  first_name: string;
  last_name: string | null;
  phone_number: string | null;
}

export interface StaffAddress {
  full_address: string;
  latitude: string | null;
  longitude: string | null;
  entrance: string | null;
  apartment: string | null;
  floor: string | null;
  courier_instructions: string | null;
}

export interface StaffSummary {
  telegram_id: number;
  first_name: string;
  last_name: string | null;
}

export interface StaffOrder {
  id: string;
  order_number: string | null;
  status: string;
  created_at: string;
  status_updated_at: string | null;
  assigned_at: string | null;
  delivered_at: string | null;
  customer: StaffCustomer;
  address: StaffAddress;
  items: Array<{ id?: string; name?: string; quantity: number; price?: number; modifications?: unknown[] }>;
  total_amount: number;
  delivery_fee: number;
  payment_method: string;
  payment_status: string | null;
  assigned_staff: StaffSummary | null;
}
```

- [ ] **Step 4: Add staff API service**

Create `frontend/src/services/staffApi.ts`:

```ts
import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse, User } from '../types/api';
import type { StaffOrder } from '../types/staff';

export const getAvailableStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/available');

export const getActiveStaffOrder = (): Promise<AxiosResponse<ApiResponse<StaffOrder | null>>> =>
  api.get('/staff/orders/active');

export const getCompletedStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/completed');

export const getStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.get(`/staff/orders/${id}`);

export const takeStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.post(`/staff/orders/${id}/take`);

export const markStaffOrderDelivered = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.post(`/staff/orders/${id}/delivered`);

export const searchAdminUsers = (query: string): Promise<AxiosResponse<ApiResponse<User[]>>> =>
  api.get('/admin/users', { params: { query } });

export const updateAdminUserRole = (
  telegramId: number,
  role: User['role'],
): Promise<AxiosResponse<ApiResponse<User>>> =>
  api.patch(`/admin/users/${telegramId}/role`, { role });
```

- [ ] **Step 5: Store current user in auth store**

In `frontend/src/stores/authStore.ts`, update imports:

```ts
import type { User } from '../types/api';
```

Update `AuthState`:

```ts
  user: User | null;
  refreshMe: () => Promise<User | null>;
```

Add initial state:

```ts
  user: null,
```

Inside `authenticate`, after `getMe()` succeeds:

```ts
        const me = meRes.data.data;
        set({ user: me });
        const lang = me?.language;
```

Add `refreshMe`:

```ts
  refreshMe: async () => {
    try {
      const meRes = await getMe();
      const user = meRes.data.data;
      set({ user });
      return user;
    } catch {
      return null;
    }
  },
```

In `logout`, set:

```ts
    set({ token: null, user: null, isAuthenticated: false, isLoading: false });
```

- [ ] **Step 6: Add temporary staff route pages**

Create `frontend/src/pages/staff/StaffOrdersPage.tsx`:

```tsx
export default function StaffOrdersPage() {
  return <main>Staff orders page</main>;
}
```

Create `frontend/src/pages/staff/StaffOrderDetailPage.tsx`:

```tsx
export default function StaffOrderDetailPage() {
  return <main>Staff order detail page</main>;
}
```

Create `frontend/src/pages/staff/StaffProfilePage.tsx`:

```tsx
export default function StaffProfilePage() {
  return <main>Staff profile page</main>;
}
```

- [ ] **Step 7: Add role-aware routes**

In `frontend/src/App.tsx`, import:

```tsx
import { Navigate } from 'react-router-dom';
import StaffOrdersPage from './pages/staff/StaffOrdersPage';
import StaffOrderDetailPage from './pages/staff/StaffOrderDetailPage';
import StaffProfilePage from './pages/staff/StaffProfilePage';
```

Add inside `App`:

```tsx
  const user = useAuthStore((state) => state.user);
  const isStaffMode = user?.role === 'staff' || user?.role === 'admin';
```

Update routes:

```tsx
      <Route path="/" element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanMenuPage />} />
      <Route path="/checkout" element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanCheckoutPage />} />
      <Route path="/order" element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanOrdersPage />} />
      <Route path="/profile" element={isStaffMode ? <StaffProfilePage /> : <ArtisanProfilePage />} />
      <Route path="/order/:orderId" element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanOrderStatusPage />} />
      <Route path="/staff/orders" element={<StaffOrdersPage />} />
      <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
```

- [ ] **Step 8: Run app tests**

Run:

```bash
cd frontend
npm test -- src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add frontend/src/types/api.ts frontend/src/types/staff.ts frontend/src/services/staffApi.ts frontend/src/stores/authStore.ts frontend/src/App.tsx frontend/src/pages/staff/StaffOrdersPage.tsx frontend/src/pages/staff/StaffOrderDetailPage.tsx frontend/src/pages/staff/StaffProfilePage.tsx frontend/src/App.test.tsx
git commit -m "feat: add role-aware staff routing"
```

---

### Task 6: Staff UI Components And Order Screens

**Files:**
- Create: `frontend/src/components/staff/StaffLayout.tsx`
- Create: `frontend/src/components/staff/StaffOrderTabs.tsx`
- Create: `frontend/src/components/staff/StaffOrderCard.tsx`
- Create: `frontend/src/components/staff/StaffPaymentBlock.tsx`
- Create: `frontend/src/components/staff/ConfirmDeliveredSheet.tsx`
- Replace: `frontend/src/pages/staff/StaffOrdersPage.tsx`
- Replace: `frontend/src/pages/staff/StaffOrderDetailPage.tsx`
- Replace: `frontend/src/pages/staff/StaffProfilePage.tsx`
- Create: `frontend/src/pages/staff/StaffOrdersPage.test.tsx`

**Interfaces:**
- Consumes: `StaffOrder` type and staff API functions from Task 5
- Produces: two-item staff bottom nav
- Produces: `Available`, `Active`, `Completed` tabbed staff delivery workflow
- Produces: cash confirmation before delivery completion

- [ ] **Step 1: Write failing staff UI tests**

Create `frontend/src/pages/staff/StaffOrdersPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffOrdersPage from './StaffOrdersPage';

const apiMocks = vi.hoisted(() => ({
  getActiveStaffOrder: vi.fn(),
  getAvailableStaffOrders: vi.fn(),
  getCompletedStaffOrders: vi.fn(),
  markStaffOrderDelivered: vi.fn(),
}));

vi.mock('../../services/staffApi', () => apiMocks);

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback ?? _key,
      i18n: { language: 'en' },
    }),
  };
});

const staffOrder = {
  id: 'order-1',
  order_number: 'A7-492',
  status: 'TAKEN_BY_COURIER',
  created_at: '2026-07-07T10:00:00Z',
  status_updated_at: null,
  assigned_at: null,
  delivered_at: null,
  customer: { telegram_id: 1, first_name: 'Azizbek', last_name: 'R.', phone_number: '+998901112233' },
  address: {
    full_address: 'Yakkasaray District, Shota Rustaveli 45',
    latitude: '41.2995',
    longitude: '69.2401',
    entrance: '2',
    apartment: '42',
    floor: '4',
    courier_instructions: null,
  },
  items: [{ id: 'item-1', name: 'Classic Somsa', quantity: 2, price: 18000 }],
  total_amount: 36000,
  delivery_fee: 0,
  payment_method: 'cash',
  payment_status: null,
  assigned_staff: null,
};

describe('StaffOrdersPage', () => {
  beforeEach(() => {
    apiMocks.getAvailableStaffOrders.mockResolvedValue({ data: { data: [staffOrder] } });
    apiMocks.getActiveStaffOrder.mockResolvedValue({ data: { data: null } });
    apiMocks.getCompletedStaffOrders.mockResolvedValue({ data: { data: [] } });
    apiMocks.markStaffOrderDelivered.mockResolvedValue({ data: { data: { ...staffOrder, status: 'DELIVERED' } } });
  });

  it('renders simplified staff nav and tabs', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
  });

  it('requires cash checkbox before confirming delivery', async () => {
    apiMocks.getActiveStaffOrder.mockResolvedValue({ data: { data: { ...staffOrder, assigned_at: '2026-07-07T10:01:00Z' } } });

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=active']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const markButton = await screen.findByRole('button', { name: /mark delivered/i });
    await userEvent.click(markButton);

    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    expect(confirmButton).toBeDisabled();

    await userEvent.click(screen.getByLabelText(/i have collected/i));
    expect(confirmButton).toBeEnabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend
npm test -- src/pages/staff/StaffOrdersPage.test.tsx
```

Expected: FAIL because staff UI components are not implemented.

- [ ] **Step 3: Add staff layout**

Create `frontend/src/components/staff/StaffLayout.tsx`:

```tsx
import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
import logo from '../../assets/logo.webp';

export default function StaffLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const activeOrders = location.pathname.startsWith('/staff/orders');
  const activeProfile = location.pathname === '/profile';

  return (
    <div style={{ minHeight: '100vh', backgroundColor: COLORS.surface, color: COLORS.onSurface, fontFamily: FONTS.body }}>
      <header style={{ position: 'fixed', top: 0, left: 0, right: 0, height: 72, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(246, 246, 246, 0.86)', backdropFilter: 'blur(12px)' }}>
        <img src={logo} alt="" style={{ width: 40, height: 40, borderRadius: '50%', position: 'absolute', left: 20 }} />
        <strong style={{ fontFamily: FONTS.headline, fontSize: 22, color: COLORS.primary, letterSpacing: 0 }}>OLOT SOMSA</strong>
      </header>

      <div style={{ paddingTop: 88, paddingBottom: 104, maxWidth: 672, margin: '0 auto' }}>{children}</div>

      <nav style={{ position: 'fixed', left: 0, right: 0, bottom: 0, height: 84, zIndex: 50, display: 'flex', justifyContent: 'space-around', alignItems: 'center', backgroundColor: 'rgba(255, 255, 255, 0.88)', backdropFilter: 'blur(12px)', boxShadow: '0 -8px 24px rgba(45,47,47,0.08)' }}>
        <Link to="/staff/orders" style={{ textDecoration: 'none', color: activeOrders ? COLORS.primary : COLORS.secondary, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <Icon name="receipt_long" fill={activeOrders} />
          <span style={{ fontSize: 13, fontWeight: 700 }}>Orders</span>
        </Link>
        <Link to="/profile" style={{ textDecoration: 'none', color: activeProfile ? COLORS.primary : COLORS.secondary, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <Icon name="person" fill={activeProfile} />
          <span style={{ fontSize: 13, fontWeight: 700 }}>Profile</span>
        </Link>
      </nav>
    </div>
  );
}
```

- [ ] **Step 4: Add tabs and reusable cards**

Create `frontend/src/components/staff/StaffOrderTabs.tsx`:

```tsx
import { COLORS, FONTS } from '../artisan/ArtisanLayout';

export type StaffOrderTab = 'available' | 'active' | 'completed';

const tabs: Array<{ key: StaffOrderTab; label: string }> = [
  { key: 'available', label: 'Available' },
  { key: 'active', label: 'Active' },
  { key: 'completed', label: 'Completed' },
];

export default function StaffOrderTabs({ active, onChange }: { active: StaffOrderTab; onChange: (tab: StaffOrderTab) => void }) {
  return (
    <div style={{ margin: '0 20px 24px', padding: 4, display: 'flex', borderRadius: 12, backgroundColor: COLORS.surfaceContainerLow }}>
      {tabs.map((tab) => {
        const selected = tab.key === active;
        return (
          <button key={tab.key} onClick={() => onChange(tab.key)} style={{ flex: 1, height: 44, border: 'none', borderRadius: 9, backgroundColor: selected ? COLORS.surfaceContainerLowest : 'transparent', color: selected ? COLORS.primary : COLORS.onSurfaceVariant, fontFamily: FONTS.body, fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
```

Create `frontend/src/components/staff/StaffPaymentBlock.tsx`:

```tsx
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
import { formatPrice } from '../../utils/format';

export default function StaffPaymentBlock({ method, status, amount, language }: { method: string; status: string | null; amount: number; language: string }) {
  const isCash = method === 'cash';
  return (
    <section style={{ padding: 20, borderRadius: 16, backgroundColor: isCash ? '#fee2d5' : COLORS.surfaceContainerLowest, color: isCash ? COLORS.primary : COLORS.onSurface, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{ width: 56, height: 56, borderRadius: '50%', backgroundColor: isCash ? '#ff7941' : COLORS.surfaceContainer, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Icon name={isCash ? 'payments' : 'credit_card'} style={{ color: isCash ? COLORS.onPrimary : COLORS.onSurfaceVariant }} />
      </div>
      <div>
        <p style={{ margin: 0, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0, color: COLORS.secondary }}>Payment Method</p>
        <strong style={{ fontFamily: FONTS.headline, fontSize: 22 }}>{isCash ? `Collect ${formatPrice(amount, language)}` : 'Paid Online'}</strong>
        <p style={{ margin: '4px 0 0', color: isCash ? COLORS.primary : COLORS.secondary }}>{isCash ? 'Cash upon delivery' : status === 'paid' ? 'Card payment completed' : 'Online payment'}</p>
      </div>
    </section>
  );
}
```

Create `frontend/src/components/staff/StaffOrderCard.tsx` and include a visible `Take Order` button when `mode="available"`:

```tsx
import { useNavigate } from 'react-router-dom';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
import type { StaffOrder } from '../../types/staff';
import { formatPrice, formatDateTime } from '../../utils/format';

function itemSummary(order: StaffOrder): string {
  return order.items.map((item) => `${item.quantity}x ${item.name || 'Item'}`).join(', ');
}

export default function StaffOrderCard({ order, mode, onTake, language }: { order: StaffOrder; mode: 'available' | 'completed'; onTake?: (order: StaffOrder) => void; language: string }) {
  const navigate = useNavigate();
  const isCash = order.payment_method === 'cash';
  return (
    <article onClick={() => navigate(`/staff/orders/${order.id}`)} style={{ margin: '0 20px 16px', padding: 18, borderRadius: 16, backgroundColor: COLORS.surfaceContainerLowest, boxShadow: '0 12px 32px -4px rgba(45,47,47,0.08)', cursor: 'pointer' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <p style={{ margin: 0, fontSize: 12, color: COLORS.secondary, textTransform: 'uppercase', fontWeight: 700 }}>Order</p>
          <h2 style={{ margin: '4px 0 0', fontFamily: FONTS.headline, fontSize: 24 }}>#{order.order_number || order.id.slice(0, 6)}</h2>
        </div>
        <strong style={{ color: COLORS.primary, fontFamily: FONTS.headline, fontSize: 20 }}>{formatPrice(order.total_amount, language)}</strong>
      </div>
      <div style={{ marginTop: 18, padding: 14, borderRadius: 12, backgroundColor: COLORS.surfaceContainerLow }}>
        <p style={{ margin: 0, fontWeight: 800 }}>{order.customer.first_name} {order.customer.last_name || ''}</p>
        <p style={{ margin: '8px 0 0', color: COLORS.onSurfaceVariant }}>{order.address.full_address}</p>
      </div>
      <p style={{ margin: '16px 0 4px', color: COLORS.secondary }}>{itemSummary(order)}</p>
      <p style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 6, color: isCash ? COLORS.onSurface : '#833e9a', fontWeight: 700 }}>
        <Icon name={isCash ? 'payments' : 'credit_card'} size={18} /> {isCash ? 'Cash on Delivery' : 'Paid Online'}
      </p>
      {mode === 'available' && (
        <button onClick={(event) => { event.stopPropagation(); onTake?.(order); }} style={{ marginTop: 18, width: '100%', height: 56, border: 'none', borderRadius: 10, background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)', color: COLORS.onPrimary, fontFamily: FONTS.headline, fontWeight: 800, fontSize: 16 }}>
          Take Order
        </button>
      )}
      {mode === 'completed' && order.delivered_at && (
        <p style={{ margin: '14px 0 0', color: COLORS.secondary }}>{formatDateTime(order.delivered_at, language)}</p>
      )}
    </article>
  );
}
```

- [ ] **Step 5: Add delivered confirmation sheet**

Create `frontend/src/components/staff/ConfirmDeliveredSheet.tsx`:

```tsx
import { useState } from 'react';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
import { formatPrice } from '../../utils/format';
import type { StaffOrder } from '../../types/staff';

export default function ConfirmDeliveredSheet({ order, language, submitting, error, onCancel, onConfirm }: { order: StaffOrder; language: string; submitting: boolean; error: string | null; onCancel: () => void; onConfirm: () => void }) {
  const isCash = order.payment_method === 'cash';
  const [collected, setCollected] = useState(!isCash);
  return (
    <div role="dialog" aria-modal="true" style={{ position: 'fixed', inset: 0, zIndex: 100, backgroundColor: 'rgba(45,47,47,0.35)', display: 'flex', alignItems: 'flex-end' }}>
      <section style={{ width: '100%', padding: '32px 24px 24px', borderTopLeftRadius: 28, borderTopRightRadius: 28, backgroundColor: COLORS.surfaceContainerLowest }}>
        <div style={{ width: 64, height: 64, borderRadius: '50%', backgroundColor: '#fee2d5', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
          <Icon name="inventory_2" size={32} style={{ color: COLORS.primary }} />
        </div>
        <h2 style={{ margin: 0, fontFamily: FONTS.headline, fontSize: 32 }}>Confirm Delivery</h2>
        <p style={{ color: COLORS.secondary, fontSize: 17 }}>Are you sure you want to mark Order #{order.order_number || order.id.slice(0, 6)} as delivered?</p>
        {isCash && (
          <label style={{ display: 'flex', gap: 16, padding: 18, borderRadius: 14, backgroundColor: COLORS.surfaceContainerLow, margin: '24px 0' }}>
            <input aria-label={`I have collected ${formatPrice(order.total_amount, language)} cash`} type="checkbox" checked={collected} onChange={(event) => setCollected(event.target.checked)} style={{ width: 24, height: 24, accentColor: COLORS.primary }} />
            <span style={{ fontWeight: 800, fontSize: 18 }}>I have collected {formatPrice(order.total_amount, language)} cash.</span>
          </label>
        )}
        {error && <p style={{ color: COLORS.error, fontWeight: 700 }}>{error}</p>}
        <button disabled={!collected || submitting} onClick={onConfirm} style={{ width: '100%', height: 56, border: 'none', borderRadius: 10, background: collected ? 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)' : COLORS.surfaceContainerHigh, color: collected ? COLORS.onPrimary : COLORS.onSurfaceVariant, fontFamily: FONTS.headline, fontWeight: 800, fontSize: 17 }}>
          {submitting ? 'Submitting...' : 'Confirm & Mark Delivered'}
        </button>
        <button onClick={onCancel} style={{ marginTop: 12, width: '100%', height: 52, border: 'none', borderRadius: 10, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, fontFamily: FONTS.headline, fontWeight: 800, fontSize: 17 }}>
          Cancel
        </button>
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Replace staff orders page with functional tabs**

Replace `frontend/src/pages/staff/StaffOrdersPage.tsx` with:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import StaffLayout from '../../components/staff/StaffLayout';
import StaffOrderTabs, { type StaffOrderTab } from '../../components/staff/StaffOrderTabs';
import StaffOrderCard from '../../components/staff/StaffOrderCard';
import StaffPaymentBlock from '../../components/staff/StaffPaymentBlock';
import ConfirmDeliveredSheet from '../../components/staff/ConfirmDeliveredSheet';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getActiveStaffOrder, getAvailableStaffOrders, getCompletedStaffOrders, markStaffOrderDelivered, takeStaffOrder } from '../../services/staffApi';
import type { StaffOrder } from '../../types/staff';

const validTabs: StaffOrderTab[] = ['available', 'active', 'completed'];

export default function StaffOrdersPage() {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = useMemo<StaffOrderTab>(() => {
    const value = params.get('tab') as StaffOrderTab | null;
    return value && validTabs.includes(value) ? value : 'available';
  }, [params]);
  const [available, setAvailable] = useState<StaffOrder[]>([]);
  const [active, setActive] = useState<StaffOrder | null>(null);
  const [completed, setCompleted] = useState<StaffOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<StaffOrder | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [availableRes, activeRes, completedRes] = await Promise.all([
        getAvailableStaffOrders(),
        getActiveStaffOrder(),
        getCompletedStaffOrders(),
      ]);
      setAvailable(availableRes.data.data || []);
      setActive(activeRes.data.data || null);
      setCompleted(completedRes.data.data || []);
    } catch {
      setError('Could not load staff orders. Try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const changeTab = (next: StaffOrderTab) => setParams({ tab: next });

  const handleTake = async (order: StaffOrder) => {
    try {
      await takeStaffOrder(order.id);
      await load();
      changeTab('active');
    } catch {
      setError('This order is no longer available.');
      await load();
    }
  };

  const handleDelivered = async () => {
    if (!confirming) return;
    setSubmitting(true);
    setError(null);
    try {
      await markStaffOrderDelivered(confirming.id);
      setConfirming(null);
      await load();
      changeTab('completed');
    } catch {
      setError('Could not mark the order delivered. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <StaffLayout>
      <StaffOrderTabs active={tab} onChange={changeTab} />
      {loading && <p style={{ padding: '24px 20px', color: COLORS.secondary }}>Loading orders...</p>}
      {error && <p style={{ margin: '0 20px 16px', color: COLORS.error, fontWeight: 700 }}>{error}</p>}
      {!loading && tab === 'available' && (
        available.length === 0 ? (
          <EmptyState title="No delivery orders available" action="Refresh" onAction={() => void load()} />
        ) : (
          available.map((order) => <StaffOrderCard key={order.id} order={order} mode="available" onTake={handleTake} language={i18n.language} />)
        )
      )}
      {!loading && tab === 'active' && (
        active ? (
          <section style={{ padding: '0 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
            <h1 style={{ margin: '0 0 4px', fontFamily: FONTS.headline, fontSize: 34 }}>Active Delivery</h1>
            <ActionCard order={active} onMarkDelivered={() => setConfirming(active)} language={i18n.language} />
          </section>
        ) : (
          <EmptyState title="No active delivery" action="View Available" onAction={() => changeTab('available')} />
        )
      )}
      {!loading && tab === 'completed' && (
        completed.length === 0 ? (
          <EmptyState title="No completed deliveries yet" />
        ) : (
          completed.map((order) => <StaffOrderCard key={order.id} order={order} mode="completed" language={i18n.language} />)
        )
      )}
      {confirming && (
        <ConfirmDeliveredSheet order={confirming} language={i18n.language} submitting={submitting} error={error} onCancel={() => setConfirming(null)} onConfirm={handleDelivered} />
      )}
    </StaffLayout>
  );
}

function EmptyState({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return (
    <div style={{ padding: '64px 20px', textAlign: 'center' }}>
      <Icon name="receipt_long" size={42} style={{ color: COLORS.outline }} />
      <h2 style={{ fontFamily: FONTS.headline }}>{title}</h2>
      {action && <button onClick={onAction} style={{ height: 48, padding: '0 24px', border: 'none', borderRadius: 10, backgroundColor: COLORS.primary, color: COLORS.onPrimary, fontWeight: 800 }}>{action}</button>}
    </div>
  );
}

function ActionCard({ order, language, onMarkDelivered }: { order: StaffOrder; language: string; onMarkDelivered: () => void }) {
  const mapHref = order.address.latitude && order.address.longitude ? `https://yandex.com/maps/?rtext=~${order.address.latitude},${order.address.longitude}&rtt=auto` : undefined;
  return (
    <>
      <section style={{ padding: 24, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest }}>
        <p style={{ margin: 0, color: COLORS.secondary }}>Customer</p>
        <h2 style={{ fontFamily: FONTS.headline }}>{order.customer.first_name} {order.customer.last_name || ''}</h2>
        {order.customer.phone_number && <a href={`tel:${order.customer.phone_number}`} style={{ display: 'block', height: 48, lineHeight: '48px', textAlign: 'center', borderRadius: 10, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, textDecoration: 'none', fontWeight: 800 }}>Call Customer</a>}
        <p style={{ color: COLORS.onSurfaceVariant }}>{order.address.full_address}</p>
        {mapHref && <a href={mapHref} target="_blank" rel="noreferrer" style={{ display: 'block', height: 48, lineHeight: '48px', textAlign: 'center', borderRadius: 10, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, textDecoration: 'none', fontWeight: 800 }}>Open Map</a>}
      </section>
      <section style={{ padding: 24, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest }}>
        <p style={{ marginTop: 0, color: COLORS.secondary }}>Order Items</p>
        {order.items.map((item, index) => <p key={`${item.id || index}`}><strong>{item.quantity}x</strong> {item.name || 'Item'}</p>)}
      </section>
      <StaffPaymentBlock method={order.payment_method} status={order.payment_status} amount={order.total_amount} language={language} />
      <button onClick={onMarkDelivered} style={{ width: '100%', height: 58, border: 'none', borderRadius: 10, background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)', color: COLORS.onPrimary, fontFamily: FONTS.headline, fontWeight: 800, fontSize: 18 }}>
        Mark Delivered
      </button>
    </>
  );
}
```

- [ ] **Step 7: Implement detail and profile pages**

Replace `frontend/src/pages/staff/StaffOrderDetailPage.tsx` with:

```tsx
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import StaffLayout from '../../components/staff/StaffLayout';
import StaffPaymentBlock from '../../components/staff/StaffPaymentBlock';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getStaffOrder, takeStaffOrder } from '../../services/staffApi';
import type { StaffOrder } from '../../types/staff';

export default function StaffOrderDetailPage() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  const [order, setOrder] = useState<StaffOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!orderId) return;
    let cancelled = false;
    setLoading(true);
    void getStaffOrder(orderId)
      .then((response) => {
        if (!cancelled) setOrder(response.data.data);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load this order.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  const handleTake = async () => {
    if (!order) return;
    setSubmitting(true);
    setError(null);
    try {
      await takeStaffOrder(order.id);
      navigate('/staff/orders?tab=active', { replace: true });
    } catch {
      setError('This order is no longer available.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <StaffLayout>
        <p style={{ padding: 20, color: COLORS.secondary }}>Loading order...</p>
      </StaffLayout>
    );
  }

  if (!order) {
    return (
      <StaffLayout>
        <section style={{ padding: 20 }}>
          <h1 style={{ fontFamily: FONTS.headline }}>Order not found</h1>
          <button onClick={() => navigate('/staff/orders')} style={{ height: 48, padding: '0 18px', border: 'none', borderRadius: 10, backgroundColor: COLORS.primary, color: COLORS.onPrimary, fontWeight: 800 }}>Back to Orders</button>
        </section>
      </StaffLayout>
    );
  }

  const mapHref = order.address.latitude && order.address.longitude
    ? `https://yandex.com/maps/?rtext=~${order.address.latitude},${order.address.longitude}&rtt=auto`
    : undefined;

  return (
    <StaffLayout>
      <main style={{ padding: '0 20px 96px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <button onClick={() => navigate('/staff/orders')} style={{ width: 44, height: 44, border: 'none', borderRadius: '50%', backgroundColor: COLORS.surfaceContainerLow }}>
          <Icon name="arrow_back" />
        </button>
        <div>
          <p style={{ margin: 0, color: COLORS.primary, fontWeight: 800, textTransform: 'uppercase' }}>Ready for pickup</p>
          <h1 style={{ margin: '8px 0 0', fontFamily: FONTS.headline, fontSize: 40 }}>Order #{order.order_number || order.id.slice(0, 6)}</h1>
        </div>

        <section style={{ padding: 20, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest }}>
          <p style={{ margin: 0, color: COLORS.secondary, textTransform: 'uppercase' }}>Customer</p>
          <h2 style={{ fontFamily: FONTS.headline }}>{order.customer.first_name} {order.customer.last_name || ''}</h2>
          {order.customer.phone_number && <a href={`tel:${order.customer.phone_number}`} style={{ display: 'block', height: 48, lineHeight: '48px', textAlign: 'center', borderRadius: 10, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, textDecoration: 'none', fontWeight: 800 }}>Call Customer</a>}
        </section>

        <section style={{ padding: 20, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest }}>
          <p style={{ margin: 0, color: COLORS.secondary, textTransform: 'uppercase' }}>Delivery Address</p>
          <p style={{ fontSize: 18, fontWeight: 700 }}>{order.address.full_address}</p>
          {mapHref && <a href={mapHref} target="_blank" rel="noreferrer" style={{ display: 'block', height: 48, lineHeight: '48px', textAlign: 'center', borderRadius: 10, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, textDecoration: 'none', fontWeight: 800 }}>Open Map</a>}
        </section>

        <section style={{ padding: 20, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest }}>
          <p style={{ marginTop: 0, color: COLORS.secondary, textTransform: 'uppercase' }}>Order Items</p>
          {order.items.map((item, index) => <p key={`${item.id || index}`}><strong>{item.quantity}x</strong> {item.name || 'Item'}</p>)}
        </section>

        <StaffPaymentBlock method={order.payment_method} status={order.payment_status} amount={order.total_amount} language={i18n.language} />
        {error && <p style={{ color: COLORS.error, fontWeight: 700 }}>{error}</p>}
      </main>
      <div style={{ position: 'fixed', left: 0, right: 0, bottom: 84, padding: 20, backgroundColor: 'rgba(246,246,246,0.88)', backdropFilter: 'blur(12px)' }}>
        <button disabled={submitting} onClick={handleTake} style={{ width: '100%', height: 58, border: 'none', borderRadius: 12, background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)', color: COLORS.onPrimary, fontFamily: FONTS.headline, fontWeight: 800, fontSize: 18 }}>
          {submitting ? 'Taking...' : 'Take Order'}
        </button>
      </div>
    </StaffLayout>
  );
}
```

Replace `frontend/src/pages/staff/StaffProfilePage.tsx` with:

```tsx
import { useEffect, useState } from 'react';
import StaffLayout from '../../components/staff/StaffLayout';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getMe } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import type { User } from '../../types/api';

export default function StaffProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const logout = useAuthStore((state) => state.logout);

  useEffect(() => {
    let cancelled = false;
    void getMe()
      .then((response) => {
        if (!cancelled) setUser(response.data.data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <StaffLayout>
      <main style={{ padding: '0 20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <h1 style={{ fontFamily: FONTS.headline, fontSize: 34, margin: 0 }}>Profile</h1>
        {loading && <p style={{ color: COLORS.secondary }}>Loading profile...</p>}
        {user && (
          <section style={{ padding: 24, borderRadius: 18, backgroundColor: COLORS.surfaceContainerLowest, textAlign: 'center' }}>
            <div style={{ width: 88, height: 88, margin: '0 auto 16px', borderRadius: '50%', background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)', color: COLORS.onPrimary, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONTS.headline, fontSize: 34, fontWeight: 800 }}>
              {(user.first_name?.[0] || 'S').toUpperCase()}
            </div>
            <h2 style={{ margin: 0, fontFamily: FONTS.headline }}>{user.first_name} {user.last_name || ''}</h2>
            <p style={{ margin: '6px 0', color: COLORS.secondary }}>{user.username ? `@${user.username}` : 'Telegram staff'}</p>
            <p style={{ margin: '6px 0', color: COLORS.primary, fontWeight: 800 }}>{user.role.toUpperCase()}</p>
            {user.phone_number && <p style={{ margin: '12px 0 0', color: COLORS.onSurface }}>{user.phone_number}</p>}
          </section>
        )}
        <button onClick={logout} style={{ height: 52, border: 'none', borderRadius: 12, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.onSurface, fontFamily: FONTS.headline, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <Icon name="logout" />
          Logout
        </button>
      </main>
    </StaffLayout>
  );
}
```

- [ ] **Step 8: Run staff UI test**

Run:

```bash
cd frontend
npm test -- src/pages/staff/StaffOrdersPage.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

Expected: all commands PASS.

- [ ] **Step 10: Commit**

Run:

```bash
git add frontend/src/components/staff frontend/src/pages/staff frontend/src/pages/staff/StaffOrdersPage.test.tsx
git commit -m "feat: build staff delivery UI"
```

---

### Task 7: End-To-End Verification And Deployment Notes

**Files:**
- Modify: `docs/superpowers/specs/2026-07-07-staff-delivery-design.md`
- Create: `docs/staff-delivery-phase-1-rollout.md`

**Interfaces:**
- Consumes: all backend and frontend work from Tasks 1-6
- Produces: deployment checklist and verification evidence

- [ ] **Step 1: Add rollout doc**

Create `docs/staff-delivery-phase-1-rollout.md`:

````markdown
# Staff Delivery Phase 1 Rollout

## Environment

Set this in production before first admin login:

```env
BOOTSTRAP_ADMIN_TELEGRAM_IDS=<admin-telegram-id>
```

## Production SQL

Apply:

```bash
psql "$DATABASE_URL" -f database/migrations/2026-07-07-staff-delivery-phase-1.sql
```

For the deployed `ssh restaurant` environment, run through WSL and the Postgres container:

```bash
ssh restaurant 'wsl bash -lc "docker exec -i restaurant_postgres psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"" ' < database/migrations/2026-07-07-staff-delivery-phase-1.sql
```

## Smoke Test

1. Login as bootstrap admin.
2. Open admin dashboard.
3. Promote one existing user to staff.
4. Login as staff in Telegram Mini App.
5. Confirm bottom nav has only Orders and Profile.
6. Confirm Orders has Available, Active, Completed.
7. Take one available `TAKEN_BY_COURIER` delivery order.
8. Confirm a second order cannot be taken while active delivery exists.
9. Mark the active delivery as delivered.
10. Confirm it appears under Completed.

## Rollback

If routing or role checks block staff unexpectedly, set affected users back to `customer`:

```sql
UPDATE users SET role = 'customer' WHERE telegram_id = <staff-telegram-id>;
```

Do not drop assignment columns during a hot rollback. They are nullable and safe to leave in place.
````

- [ ] **Step 2: Update design spec status**

In `docs/superpowers/specs/2026-07-07-staff-delivery-design.md`, change:

```markdown
Status: Draft for review
```

to:

```markdown
Status: Approved for Phase 1 implementation
```

- [ ] **Step 3: Run backend verification**

Run:

```bash
cd backend
source .venv/bin/activate
pytest -v
ruff check .
```

Expected: PASS.

- [ ] **Step 4: Run frontend verification**

Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 5: Start local app and manually inspect staff UI**

Run:

```bash
docker compose up --build
```

Expected:

- `restaurant_backend` becomes healthy.
- `restaurant_frontend` becomes healthy.
- `restaurant_caddy` becomes healthy.
- App is reachable through the configured local Caddy URL.

Manual checks:

- Staff bottom nav has only `Orders` and `Profile`.
- `Available`, `Active`, and `Completed` tabs do not overlap content.
- `Take Order` is visible on available cards and detail screen.
- Cash confirmation checkbox gates the delivered button.
- Completed history heading is not covered by the tabs.

- [ ] **Step 6: Commit docs and final verification updates**

Run:

```bash
git add docs/staff-delivery-phase-1-rollout.md docs/superpowers/specs/2026-07-07-staff-delivery-design.md
git commit -m "docs: add staff delivery rollout notes"
```

---

## Self-Review Checklist

- Spec coverage: Tasks 1-4 cover roles, assignment, secure backend endpoints, and local terminal delivery state. Tasks 5-6 cover the two-item staff UI and staff workflow. Task 7 covers rollout.
- No batching: no task adds multiple active orders, route optimization, or batch tables.
- No `delivered_by_staff_id`: the plan only uses `assigned_staff_id`, `assigned_at`, and `delivered_at`.
- Type consistency: backend uses `StaffOrderResponse`; frontend uses `StaffOrder`.
- Security: staff/admin endpoints require server-side role checks; order mutations use row locks; staff completion checks assigned staff identity.
- Design consistency: staff layout uses existing `COLORS`, `FONTS`, `Icon`, logo, and the two-item bottom nav.
