# Admin and Staff Table Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give staff and admins a read-only workspace that lists every current AliPOS table, aggregates active mini-app table orders safely, exposes original order details, and reuses the customer menu as a browse-only catalog.

**Architecture:** A focused backend table-workspace service joins the cached AliPOS hall/table directory to local `inplace` orders, durably throttles verified per-order status reads, and returns privacy-minimized overview/detail contracts. The React staff shell gains a Tables destination, visibility-aware polling, table overview/detail pages, and a shared menu catalog with explicit interactive and browse-only modes.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy async, PostgreSQL 16, httpx, pytest, React 19, TypeScript 5.7, Zustand 5, React Router 6, Vitest, Testing Library, i18next.

## Global Constraints

- The source design is `docs/superpowers/specs/2026-07-15-admin-staff-table-inspection-design.md`.
- Only `staff` and `admin` may access the new backend endpoints and frontend routes.
- Display every table from the current AliPOS directory; overlay only mini-app-created `inplace` orders.
- Never label a table free, occupied, available, or reserved. Use `mini-app orders` wording.
- Only synchronized orders contribute to combined item counts and monetary totals.
- Show queued/sending orders as processing and failed/unknown orders as attention; neither contributes to synchronized totals.
- Exclude unpaid/pre-order payment states and terminal delivered/cancelled states.
- Preserve original order boundaries even when table-level items and totals are combined.
- The staff menu is browse-only: no cart subscriptions, quantity controls, table context, checkout, or mutations.
- Poll visible staff pages every 15 seconds; throttle AliPOS status attempts durably to 30 seconds; mark data stale after 60 seconds; cap status-read concurrency at five.
- Use only verified AliPOS hall/table and known-order reads. Do not depend on the unverified status webhook.
- Do not return customer identity/contact/address data, access tokens, Multicard identifiers, checkout URLs, provider bodies, or OAuth data.
- Preserve existing customer ordering, delivery staff rules, admin role management, payment, refund, and cancellation behavior.
- Add Uzbek, Russian, and English copy; use text/icons in addition to color and touch targets of at least 44 by 44 pixels.
- Add no new runtime dependency.

---

### Task 1: Persist status-refresh metadata

**Files:**
- Modify: `backend/app/models/models.py:81-189`
- Modify: `backend/tests/test_order_model.py`
- Modify: `database/init.sql:35-177`
- Create: `database/migrations/2026-07-15-staff-table-inspection.sql`

**Interfaces:**
- Produces `Order.alipos_status_check_attempted_at: datetime | None`.
- Produces `Order.alipos_status_checked_at: datetime | None`.
- Produces partial index `idx_orders_inplace_workspace` for later workspace and refresh queries.

- [ ] **Step 1: Write the failing model/index contract test**

Append this test to `backend/tests/test_order_model.py`:

```python
def test_order_metadata_declares_staff_table_refresh_fields_and_index():
    assert {
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_order_model.py::test_order_metadata_declares_staff_table_refresh_fields_and_index -q
```

Expected: FAIL because the columns/index do not exist.

- [ ] **Step 3: Add the ORM fields and partial index**

Add these fields beside `status_updated_at` in `Order`:

```python
alipos_status_check_attempted_at: Mapped[datetime.datetime | None] = mapped_column()
alipos_status_checked_at: Mapped[datetime.datetime | None] = mapped_column()
```

Add this entry to `Order.__table_args__`:

```python
Index(
    "idx_orders_inplace_workspace",
    "table_id",
    "alipos_sync_status",
    "status",
    "alipos_status_check_attempted_at",
    postgresql_where=text("discriminator = 'inplace'"),
),
```

Add these exact nullable columns immediately after `status_updated_at` in the initial `CREATE TABLE orders` definition in `database/init.sql`:

```sql
alipos_status_check_attempted_at TIMESTAMP,
alipos_status_checked_at TIMESTAMP,
```

Add the following to the additive compatibility section so an existing volume initialized from an older file also converges:

```sql
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_check_attempted_at TIMESTAMP;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_checked_at TIMESTAMP;
```

Add this index after the existing order indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_inplace_workspace
    ON orders(table_id, alipos_sync_status, status, alipos_status_check_attempted_at)
    WHERE discriminator = 'inplace';
```

Create `database/migrations/2026-07-15-staff-table-inspection.sql`:

```sql
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_check_attempted_at TIMESTAMP;
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS alipos_status_checked_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_orders_inplace_workspace
    ON orders(table_id, alipos_sync_status, status, alipos_status_check_attempted_at)
    WHERE discriminator = 'inplace';
```

- [ ] **Step 4: Run the model tests and prove migration idempotency**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_order_model.py -q
cd .. && rg -n "alipos_status_check_attempted_at|alipos_status_checked_at|idx_orders_inplace_workspace" backend/app/models/models.py database/init.sql database/migrations/2026-07-15-staff-table-inspection.sql
set -a
source .env
set +a
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < database/migrations/2026-07-15-staff-table-inspection.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < database/migrations/2026-07-15-staff-table-inspection.sql
```

Expected: all model tests PASS, every schema surface contains the new names, and both migration applications exit zero. If the local Postgres service is not running, start only `postgres` with `docker compose up -d postgres`, wait for its health check, then rerun the two commands; do not silently skip this proof.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add backend/app/models/models.py backend/tests/test_order_model.py database/init.sql database/migrations/2026-07-15-staff-table-inspection.sql
git commit -m "feat: persist table inspection freshness"
```

---

### Task 2: Add a stale-aware hall/table directory snapshot

**Files:**
- Modify: `backend/app/services/alipos_api.py:1-180`
- Modify: `backend/app/services/table_access_service.py:1-89`
- Create: `backend/tests/test_alipos_api.py`
- Modify: `backend/tests/test_table_access_service.py`

**Interfaces:**
- Produces `HallsTablesSnapshot(payload, stale, last_success_at)`.
- Produces `get_halls_and_tables_snapshot() -> HallsTablesSnapshot`.
- Produces pure `parse_table_directory(payload: dict) -> list[TableDirectoryEntry]`.
- Preserves `get_halls_and_tables() -> dict` for customer table resolution.

- [ ] **Step 1: Write failing fresh/stale/no-cache tests**

Create `backend/tests/test_alipos_api.py`:

```python
import datetime
from unittest.mock import AsyncMock

import pytest

from app.services import alipos_api


DIRECTORY = {
    "halls": [{"id": "22222222-2222-4222-8222-222222222222", "title": "Main", "servicePercent": 10}],
    "tables": [{"id": "11111111-1111-4111-8111-111111111111", "title": "Stol 1", "hallId": "22222222-2222-4222-8222-222222222222"}],
}


class JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def reset_table_cache(monkeypatch):
    monkeypatch.setattr(alipos_api, "_tables_cache", None)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", None)


@pytest.mark.asyncio
async def test_halls_tables_snapshot_records_fresh_success(monkeypatch):
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(DIRECTORY)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is False
    assert snapshot.last_success_at.tzinfo == datetime.UTC


@pytest.mark.asyncio
async def test_halls_tables_snapshot_reuses_fresh_cache_without_provider_call(monkeypatch):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    request = AsyncMock()
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", float("inf"))
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(alipos_api, "_api_request", request)

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.stale is False
    assert snapshot.last_success_at == last_success
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_halls_tables_snapshot_returns_stale_cache_after_refresh_error(monkeypatch):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True
    assert snapshot.last_success_at == last_success


@pytest.mark.asyncio
async def test_halls_tables_snapshot_uses_stale_cache_for_malformed_success(monkeypatch):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse({"halls": "not-a-list", "tables": []})),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True


@pytest.mark.parametrize(
    "malformed",
    [
        {
            "halls": [{"id": "not-a-uuid", "title": "Broken", "servicePercent": 10}],
            "tables": [],
        },
        {
            "halls": DIRECTORY["halls"],
            "tables": [{"id": "not-a-uuid", "title": "Broken", "hallId": DIRECTORY["halls"][0]["id"]}],
        },
        {
            "halls": DIRECTORY["halls"],
            "tables": [{"id": "44444444-4444-4444-8444-444444444444", "title": "Orphan", "hallId": "55555555-5555-4555-8555-555555555555"}],
        },
    ],
)
@pytest.mark.asyncio
async def test_malformed_row_never_replaces_last_complete_directory(monkeypatch, malformed):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(malformed)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True
    assert snapshot.last_success_at == last_success


@pytest.mark.asyncio
async def test_malformed_row_raises_when_no_complete_directory_exists(monkeypatch):
    malformed = {
        "halls": DIRECTORY["halls"],
        "tables": [{"id": "not-a-uuid", "title": "Broken", "hallId": DIRECTORY["halls"][0]["id"]}],
    }
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(malformed)),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables_snapshot()


@pytest.mark.asyncio
async def test_halls_tables_snapshot_raises_without_any_cache(monkeypatch):
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables_snapshot()


@pytest.mark.asyncio
async def test_empty_halls_tables_directory_is_a_valid_fresh_success(monkeypatch):
    empty = {"halls": [], "tables": []}
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(empty)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == empty
    assert snapshot.stale is False


@pytest.mark.asyncio
async def test_legacy_customer_directory_rejects_stale_fallback(monkeypatch):
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(
        alipos_api,
        "_tables_cache_last_success_at",
        datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC),
    )
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables()
```

Add this parser test to `backend/tests/test_table_access_service.py`:

```python
def test_parse_table_directory_joins_a_validated_complete_directory():
    from app.services.table_access_service import parse_table_directory

    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Asosiy zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)},
        ],
    }

    assert parse_table_directory(payload) == [_entry()]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_alipos_api.py tests/test_table_access_service.py::test_parse_table_directory_joins_a_validated_complete_directory -q
```

Expected: FAIL because the snapshot type/function, last-success cache, and parser do not exist.

- [ ] **Step 3: Implement the snapshot while preserving the existing API**

Add to `backend/app/services/alipos_api.py`:

```python
import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class HallsTablesSnapshot:
    payload: dict
    stale: bool
    last_success_at: datetime.datetime


_tables_cache_last_success_at: datetime.datetime | None = None


class HallsTablesUnavailable(RuntimeError):
    pass


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _decode_halls_tables(response) -> dict:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("AliPOS table directory must be an object")
    if not isinstance(payload.get("halls"), list):
        raise ValueError("AliPOS table directory halls must be a list")
    if not isinstance(payload.get("tables"), list):
        raise ValueError("AliPOS table directory tables must be a list")
    hall_ids: set[uuid.UUID] = set()
    for index, hall in enumerate(payload["halls"]):
        if not isinstance(hall, dict):
            raise ValueError(f"AliPOS hall {index} must be an object")
        try:
            hall_id = uuid.UUID(str(hall["id"]))
            service_percent = Decimal(str(hall.get("servicePercent") or 0))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"AliPOS hall {index} is malformed") from exc
        if not service_percent.is_finite() or hall_id in hall_ids:
            raise ValueError(f"AliPOS hall {index} is malformed")
        hall_ids.add(hall_id)
    table_ids: set[uuid.UUID] = set()
    for index, table in enumerate(payload["tables"]):
        if not isinstance(table, dict):
            raise ValueError(f"AliPOS table {index} must be an object")
        try:
            table_id = uuid.UUID(str(table["id"]))
            hall_id = uuid.UUID(str(table["hallId"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"AliPOS table {index} is malformed") from exc
        if table_id in table_ids or hall_id not in hall_ids:
            raise ValueError(f"AliPOS table {index} is malformed")
        table_ids.add(table_id)
    return payload


async def get_halls_and_tables_snapshot() -> HallsTablesSnapshot:
    global _tables_cache, _tables_cache_expires_at, _tables_cache_last_success_at

    if _tables_cache is not None and time.monotonic() < _tables_cache_expires_at:
        if _tables_cache_last_success_at is None:
            raise HallsTablesUnavailable("Table cache is missing freshness metadata")
        return HallsTablesSnapshot(
            _tables_cache,
            False,
            _tables_cache_last_success_at,
        )

    try:
        response = await _api_request(
            "GET",
            f"/api/Integration/v1/restaurant/{settings.alipos_restaurant_id}/halls-and-tables",
        )
        payload = _decode_halls_tables(response)
    except Exception as exc:
        if _tables_cache is None or _tables_cache_last_success_at is None:
            raise HallsTablesUnavailable("Table directory is unavailable") from exc
        return HallsTablesSnapshot(
            _tables_cache,
            True,
            _tables_cache_last_success_at,
        )

    _tables_cache = payload
    _tables_cache_expires_at = time.monotonic() + _MENU_TTL
    _tables_cache_last_success_at = _utcnow()
    return HallsTablesSnapshot(
        _tables_cache,
        False,
        _tables_cache_last_success_at,
    )


async def get_halls_and_tables() -> dict:
    snapshot = await get_halls_and_tables_snapshot()
    if snapshot.stale:
        # Stale fallback is inspection-only. Customer resolution and token
        # restoration must never accept a table removed from the live directory.
        raise HallsTablesUnavailable("A fresh table directory is required")
    return snapshot.payload
```

The snapshot decoder validates every hall and table row, UUID relationship, service percentage, and duplicate ID before replacing the complete cache. A malformed refresh therefore becomes a stale workspace response when a prior complete snapshot exists, or `HallsTablesUnavailable` when it does not. The legacy customer-facing `get_halls_and_tables()` path deliberately rejects stale snapshots so QR/code resolution, restore, access-token validation, and manifest generation preserve their current live-directory safety boundary.

Replace the parsing body at the top of `get_table_directory()` with a pure function in `backend/app/services/table_access_service.py`:

```python
# Extend the existing decimal import to:
from decimal import Decimal, InvalidOperation


def parse_table_directory(payload: dict) -> list[TableDirectoryEntry]:
    halls: dict[uuid.UUID, tuple[str, Decimal]] = {}
    for hall in payload.get("halls", []):
        try:
            hall_id = uuid.UUID(str(hall["id"]))
        except (KeyError, TypeError, ValueError):
            continue
        try:
            service_percent = Decimal(str(hall.get("servicePercent") or 0))
        except InvalidOperation:
            continue
        halls[hall_id] = (str(hall.get("title") or ""), service_percent)

    entries: list[TableDirectoryEntry] = []
    for table in payload.get("tables", []):
        try:
            table_id = uuid.UUID(str(table["id"]))
            hall_id = uuid.UUID(str(table["hallId"]))
        except (KeyError, TypeError, ValueError):
            continue
        hall = halls.get(hall_id)
        if hall is None:
            continue
        hall_title, service_percent = hall
        entries.append(
            TableDirectoryEntry(
                table_id=table_id,
                table_title=str(table.get("title") or ""),
                hall_id=hall_id,
                hall_title=hall_title,
                service_percent=service_percent,
            )
        )
    return entries


async def get_table_directory() -> list[TableDirectoryEntry]:
    return parse_table_directory(await alipos_api.get_halls_and_tables())
```

- [ ] **Step 4: Run directory and customer table regression tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_alipos_api.py tests/test_table_access_service.py tests/api/test_tables.py -q
```

Expected: PASS, including existing customer QR/manual-code behavior.

- [ ] **Step 5: Commit the directory slice**

```bash
git add backend/app/services/alipos_api.py backend/app/services/table_access_service.py backend/tests/test_alipos_api.py backend/tests/test_table_access_service.py
git commit -m "feat: retain stale table directory"
```

---

### Task 3: Build the privacy-minimized table aggregation read model

**Files:**
- Create: `backend/app/schemas/staff_table.py`
- Create: `backend/app/services/staff_table_service.py`
- Create: `backend/tests/test_staff_table_service.py`

**Interfaces:**
- Produces `classify_table_order(order) -> Literal["synchronized", "processing", "attention"] | None`.
- Produces `aggregate_order_items(orders) -> list[StaffTableItemResponse]`.
- Produces `build_staff_tables_overview(directory, orders, freshness) -> StaffTablesOverviewResponse`.
- Produces `build_staff_table_detail(table_id, directory, orders, freshness) -> StaffTableDetailResponse | None`.

- [ ] **Step 1: Write failing classification, aggregation, and privacy tests**

Create `backend/tests/test_staff_table_service.py` with focused model objects:

```python
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
        "items": [{
            "id": "somsa",
            "name": "Classic Somsa",
            "quantity": 1,
            "price": 18000,
            "modifications": [],
        }],
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
    assert classify_table_order(make_order(alipos_sync_status="sending")) == "processing"
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
    assert classify_table_order(make_order(status=status, alipos_sync_status=sync)) is None


def test_online_order_requires_confirmed_payment_for_synced_or_processing():
    assert classify_table_order(make_order(
        payment_method="rahmat", payment_status="pending"
    )) is None
    assert classify_table_order(make_order(
        payment_method="rahmat", payment_status="paid"
    )) == "synchronized"


def test_aggregate_items_keeps_different_modifier_signatures_separate():
    plain = make_order()
    spicy = make_order(items=[{
        "id": "somsa",
        "name": "Classic Somsa",
        "quantity": 1,
        "price": 18000,
        "modifications": [{"id": "spicy", "name": "Spicy", "quantity": 1, "price": 1000}],
    }])

    items = aggregate_order_items([plain, plain, spicy])

    assert [(item.quantity, item.line_total) for item in items] == [
        (2.0, 36000.0),
        (1.0, 19000.0),
    ]


def test_aggregate_items_normalizes_decimal_spelling_and_modifier_order():
    first = make_order(items=[{
        "id": "combo",
        "name": "Combo",
        "quantity": 1,
        "price": 18000,
        "modifications": [
            {"id": "a", "name": "A", "quantity": 1, "price": 500},
            {"id": "b", "name": "B", "quantity": 1, "price": 1000},
        ],
    }])
    second = make_order(items=[{
        "id": "combo",
        "name": "Renamed copy",
        "quantity": "2.0",
        "price": "18000.0",
        "modifications": [
            {"id": "b", "name": "B", "quantity": "1.0", "price": "1000.00"},
            {"id": "a", "name": "A", "quantity": "1", "price": "500.0"},
        ],
    }])

    items = aggregate_order_items([first, second])

    assert len(items) == 1
    assert items[0].quantity == 3
    assert items[0].line_total == 57000


def test_aggregate_items_splits_product_price_and_modifier_signature_changes():
    variants = [
        make_order(items=[{"id": "a", "name": "Same", "quantity": 1, "price": 100, "modifications": []}]),
        make_order(items=[{"id": "b", "name": "Same", "quantity": 1, "price": 100, "modifications": []}]),
        make_order(items=[{"id": "a", "name": "Same", "quantity": 1, "price": 101, "modifications": []}]),
        make_order(items=[{"id": "a", "name": "Same", "quantity": 1, "price": 100, "modifications": [{"id": "m", "quantity": 1, "price": 1}]}]),
        make_order(items=[{"id": "a", "name": "Same", "quantity": 1, "price": 100, "modifications": [{"id": "m", "quantity": 2, "price": 1}]}]),
        make_order(items=[{"id": "a", "name": "Same", "quantity": 1, "price": 100, "modifications": [{"id": "m", "quantity": 1, "price": 2}]}]),
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
        items=[{
            "id": "legacy", "name": "Legacy", "quantity": 1,
            "price": 999, "modifications": [],
        }],
        items_cost=Decimal("12345"),
        delivery_fee=Decimal("0"),
        total_amount=Decimal("13702"),
    )

    result = build_staff_tables_overview(
        [directory_entry()], [persisted], freshness()
    ).halls[0].tables[0]

    assert result.items_cost == 12345
    assert result.service_amount == 1357
    assert result.total_amount == 13702


def test_overview_is_compact_but_detail_is_complete_and_preserves_orders():
    first = make_order(items=[
        {"id": "a", "name": "A", "quantity": 1, "price": 100, "modifications": []},
        {"id": "b", "name": "B", "quantity": 1, "price": 200, "modifications": []},
    ])
    second = make_order(items=[
        {"id": "c", "name": "C", "quantity": 1, "price": 300, "modifications": []},
    ], items_cost=Decimal("300"), total_amount=Decimal("330"),
        created_at=datetime.datetime(2026, 7, 15, 9, 1))

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
        "not_synchronized", "verify_in_pos",
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
            return set(value) | set().union(*(collect_keys(item) for item in value.values()))
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
        "id", "name", "quantity", "price", "modifications",
    }
```

- [ ] **Step 2: Run the service tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_staff_table_service.py -q
```

Expected: collection FAIL because the schemas/service do not exist.

- [ ] **Step 3: Define the exact response contract**

Create `backend/app/schemas/staff_table.py` with these models:

```python
import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field

StaffTableSyncState = Literal["synchronized", "processing", "attention"]
StaffTablePaymentMethod = Literal["cash", "online"]
StaffTablePaymentStatus = Literal["paid"]
StaffTableSyncLabel = Literal[
    "synchronized",
    "processing",
    "not_synchronized",
    "verify_in_pos",
]


class StaffTableModifierResponse(BaseModel):
    id: str
    name: str | None = None
    quantity: float
    price: float


class StaffTableOrderItemResponse(BaseModel):
    id: str
    name: str | None = None
    quantity: float
    price: float
    modifications: list[StaffTableModifierResponse] = Field(default_factory=list)


class StaffTableItemResponse(StaffTableOrderItemResponse):
    line_total: float


class StaffTableOrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str | None = None
    created_at: datetime.datetime
    status: str
    sync_state: StaffTableSyncState
    sync_label: StaffTableSyncLabel
    payment_method: StaffTablePaymentMethod
    payment_status: StaffTablePaymentStatus | None = None
    items: list[StaffTableOrderItemResponse]
    items_cost: float
    service_amount: float
    total_amount: float


class StaffTableSummaryResponse(BaseModel):
    table_id: uuid.UUID
    table_title: str
    hall_id: uuid.UUID | None = None
    hall_title: str | None = None
    service_percent: float
    is_listed: bool
    synchronized_order_count: int
    processing_order_count: int
    attention_order_count: int
    combined_item_count: float
    combined_line_count: int
    combined_items: list[StaffTableItemResponse]
    items_cost: float
    service_amount: float
    total_amount: float


class StaffHallResponse(BaseModel):
    hall_id: uuid.UUID | None = None
    hall_title: str | None = None
    service_percent: float | None = None
    is_listed: bool
    tables: list[StaffTableSummaryResponse]


class StaffTablesFreshnessResponse(BaseModel):
    generated_at: datetime.datetime
    directory_stale: bool
    directory_last_success_at: datetime.datetime
    order_status_stale: bool
    order_status_oldest_success_at: datetime.datetime | None = None


class StaffTablesOverviewResponse(BaseModel):
    freshness: StaffTablesFreshnessResponse
    halls: list[StaffHallResponse]


class StaffTableDetailResponse(BaseModel):
    freshness: StaffTablesFreshnessResponse
    table: StaffTableSummaryResponse
    orders: list[StaffTableOrderResponse]
```

- [ ] **Step 4: Implement pure classification and aggregation**

Create `backend/app/services/staff_table_service.py` with these constants and public pure functions. Use `Decimal(str(value or 0))` for every arithmetic input and convert only response values to `float`:

```python
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.models.models import Order
from app.schemas.staff_table import (
    StaffHallResponse,
    StaffTableDetailResponse,
    StaffTableItemResponse,
    StaffTableModifierResponse,
    StaffTableOrderResponse,
    StaffTableOrderItemResponse,
    StaffTableSummaryResponse,
    StaffTableSyncLabel,
    StaffTableSyncState,
    StaffTablesFreshnessResponse,
    StaffTablesOverviewResponse,
)
from app.services.order_status_service import normalize_order_status
from app.services.table_access_service import TableDirectoryEntry

TERMINAL_TABLE_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}
PRE_ORDER_STATUSES = {"AWAITING_PAYMENT", "PAYMENT_FAILED", "PAYMENT_REVIEW"}
PROCESSING_SYNC_STATES = {"queued", "sending"}
ATTENTION_SYNC_STATES = {"failed", "unknown"}


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _payment_ready(order: Order) -> bool:
    return order.payment_method == "cash" or order.payment_status == "paid"


def classify_table_order(order: Order) -> StaffTableSyncState | None:
    if order.discriminator != "inplace" or order.table_id is None:
        return None
    status = normalize_order_status(order.status)
    if status in TERMINAL_TABLE_STATUSES or status in PRE_ORDER_STATUSES:
        return None
    sync = str(order.alipos_sync_status or "").lower()
    if sync == "awaiting_payment":
        return None
    if sync == "synced" and _payment_ready(order):
        return "synchronized"
    if sync in PROCESSING_SYNC_STATES and _payment_ready(order):
        return "processing"
    if sync in ATTENTION_SYNC_STATES:
        return "attention"
    return None


def _modifier_signature(modifications: list[dict]) -> tuple:
    return tuple(sorted(
        (
            str(modifier.get("id") or ""),
            _decimal(modifier.get("quantity")),
            _decimal(modifier.get("price")),
        )
        for modifier in modifications
    ))


def _safe_modifiers(modifications: list[dict]) -> list[StaffTableModifierResponse]:
    return [
        StaffTableModifierResponse(
            id=str(modifier.get("id") or ""),
            name=modifier.get("name"),
            quantity=float(_decimal(modifier.get("quantity"))),
            price=float(_decimal(modifier.get("price"))),
        )
        for modifier in modifications
    ]


def _safe_order_items(items: list[dict]) -> list[StaffTableOrderItemResponse]:
    return [
        StaffTableOrderItemResponse(
            id=str(item.get("id") or ""),
            name=item.get("name"),
            quantity=float(_decimal(item.get("quantity"))),
            price=float(_decimal(item.get("price"))),
            modifications=_safe_modifiers(list(item.get("modifications") or [])),
        )
        for item in items
    ]


def aggregate_order_items(orders: list[Order]) -> list[StaffTableItemResponse]:
    buckets: dict[tuple, dict] = {}
    for order in orders:
        for item in order.items or []:
            modifications = list(item.get("modifications") or [])
            key = (
                str(item.get("id") or ""),
                _decimal(item.get("price")),
                _modifier_signature(modifications),
            )
            quantity = _decimal(item.get("quantity"))
            line_total = _decimal(item.get("price")) * quantity + sum(
                _decimal(modifier.get("price")) * _decimal(modifier.get("quantity"))
                for modifier in modifications
            )
            if key not in buckets:
                buckets[key] = {
                    "id": str(item.get("id") or ""),
                    "name": item.get("name"),
                    "quantity": Decimal("0"),
                    "price": _decimal(item.get("price")),
                    "modifications": modifications,
                    "line_total": Decimal("0"),
                }
            buckets[key]["quantity"] += quantity
            buckets[key]["line_total"] += line_total
    return [
        StaffTableItemResponse(
            id=value["id"],
            name=value["name"],
            quantity=float(value["quantity"]),
            price=float(value["price"]),
            modifications=_safe_modifiers(value["modifications"]),
            line_total=float(value["line_total"]),
        )
        for _, value in sorted(buckets.items(), key=lambda pair: pair[0])
    ]
```

Add the complete bucket and response builders below. The overview deliberately returns at most two combined lines per table; `combined_line_count` lets the card show `+N more`. Detail calls the same builder without a limit and therefore returns the complete combined set.

```python
@dataclass
class _TableBucket:
    table_id: uuid.UUID
    table_title: str
    hall_id: uuid.UUID | None
    hall_title: str | None
    service_percent: Decimal
    is_listed: bool
    orders: list[tuple[Order, StaffTableSyncState]] = field(default_factory=list)


def _order_sort_key(order: Order) -> tuple[datetime.datetime, str]:
    return order.created_at, str(order.id)


def _build_buckets(
    directory: list[TableDirectoryEntry],
    orders: list[Order],
) -> dict[uuid.UUID, _TableBucket]:
    buckets = {
        entry.table_id: _TableBucket(
            table_id=entry.table_id,
            table_title=entry.table_title,
            hall_id=entry.hall_id,
            hall_title=entry.hall_title,
            service_percent=entry.service_percent,
            is_listed=True,
        )
        for entry in directory
    }
    # Newest first makes a removed table's persisted snapshot deterministic.
    for order in sorted(orders, key=_order_sort_key, reverse=True):
        sync_state = classify_table_order(order)
        if sync_state is None or order.table_id is None:
            continue
        bucket = buckets.get(order.table_id)
        if bucket is None:
            bucket = _TableBucket(
                table_id=order.table_id,
                table_title=order.table_title or "",
                hall_id=order.hall_id,
                hall_title=order.hall_title,
                service_percent=_decimal(order.service_percent),
                is_listed=False,
            )
            buckets[order.table_id] = bucket
        bucket.orders.append((order, sync_state))
    return buckets


def _sync_label(
    order: Order,
    sync_state: StaffTableSyncState,
) -> StaffTableSyncLabel:
    if sync_state == "synchronized":
        return "synchronized"
    if sync_state == "processing":
        return "processing"
    return (
        "not_synchronized"
        if str(order.alipos_sync_status or "").lower() == "failed"
        else "verify_in_pos"
    )


def _order_response(
    order: Order,
    sync_state: StaffTableSyncState,
) -> StaffTableOrderResponse:
    return StaffTableOrderResponse(
        id=order.id,
        order_number=order.order_number,
        created_at=order.created_at,
        status=normalize_order_status(order.status),
        sync_state=sync_state,
        sync_label=_sync_label(order, sync_state),
        payment_method="cash" if order.payment_method == "cash" else "online",
        payment_status="paid" if order.payment_status == "paid" else None,
        items=_safe_order_items(list(order.items or [])),
        items_cost=float(_decimal(order.items_cost)),
        service_amount=float(
            _decimal(order.total_amount)
            - _decimal(order.items_cost)
            - _decimal(order.delivery_fee)
        ),
        total_amount=float(_decimal(order.total_amount)),
    )


def _summary(
    bucket: _TableBucket,
    combined_item_limit: int | None,
) -> StaffTableSummaryResponse:
    synchronized = [
        order for order, state in bucket.orders if state == "synchronized"
    ]
    all_combined_items = aggregate_order_items(synchronized)
    visible_combined_items = (
        all_combined_items
        if combined_item_limit is None
        else all_combined_items[:combined_item_limit]
    )
    items_cost = sum((_decimal(order.items_cost) for order in synchronized), Decimal("0"))
    total_amount = sum(
        (_decimal(order.total_amount) for order in synchronized),
        Decimal("0"),
    )
    service_amount = sum(
        (
            _decimal(order.total_amount)
            - _decimal(order.items_cost)
            - _decimal(order.delivery_fee)
            for order in synchronized
        ),
        Decimal("0"),
    )
    return StaffTableSummaryResponse(
        table_id=bucket.table_id,
        table_title=bucket.table_title,
        hall_id=bucket.hall_id,
        hall_title=bucket.hall_title,
        service_percent=float(bucket.service_percent),
        is_listed=bucket.is_listed,
        synchronized_order_count=len(synchronized),
        processing_order_count=sum(
            state == "processing" for _, state in bucket.orders
        ),
        attention_order_count=sum(
            state == "attention" for _, state in bucket.orders
        ),
        combined_item_count=float(
            sum((_decimal(item.quantity) for item in all_combined_items), Decimal("0"))
        ),
        combined_line_count=len(all_combined_items),
        combined_items=visible_combined_items,
        items_cost=float(items_cost),
        service_amount=float(service_amount),
        total_amount=float(total_amount),
    )


def build_staff_tables_overview(
    directory: list[TableDirectoryEntry],
    orders: list[Order],
    freshness: StaffTablesFreshnessResponse,
) -> StaffTablesOverviewResponse:
    buckets = _build_buckets(directory, orders)
    listed_halls: dict[uuid.UUID, StaffHallResponse] = {}
    unlisted_tables: list[StaffTableSummaryResponse] = []
    for bucket in buckets.values():
        summary = _summary(bucket, combined_item_limit=2)
        if not bucket.is_listed:
            unlisted_tables.append(summary)
            continue
        assert bucket.hall_id is not None
        hall = listed_halls.setdefault(
            bucket.hall_id,
            StaffHallResponse(
                hall_id=bucket.hall_id,
                hall_title=bucket.hall_title,
                service_percent=float(bucket.service_percent),
                is_listed=True,
                tables=[],
            ),
        )
        hall.tables.append(summary)

    halls = list(listed_halls.values())
    if unlisted_tables:
        halls.append(
            StaffHallResponse(
                hall_id=None,
                hall_title=None,
                service_percent=None,
                is_listed=False,
                tables=unlisted_tables,
            )
        )
    return StaffTablesOverviewResponse(freshness=freshness, halls=halls)


def build_staff_table_detail(
    table_id: uuid.UUID,
    directory: list[TableDirectoryEntry],
    orders: list[Order],
    freshness: StaffTablesFreshnessResponse,
) -> StaffTableDetailResponse | None:
    bucket = _build_buckets(directory, orders).get(table_id)
    if bucket is None:
        return None
    original_orders = sorted(
        bucket.orders,
        key=lambda pair: _order_sort_key(pair[0]),
        reverse=True,
    )
    return StaffTableDetailResponse(
        freshness=freshness,
        table=_summary(bucket, combined_item_limit=None),
        orders=[_order_response(order, state) for order, state in original_orders],
    )
```

- [ ] **Step 5: Run tests and commit the read model**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_staff_table_service.py -q
```

Expected: PASS.

```bash
git add backend/app/schemas/staff_table.py backend/app/services/staff_table_service.py backend/tests/test_staff_table_service.py
git commit -m "feat: aggregate staff table activity"
```

---

### Task 4: Reconcile known statuses and expose staff table endpoints

**Files:**
- Modify: `backend/app/services/staff_table_service.py`
- Modify: `backend/app/routers/staff.py`
- Modify: `backend/tests/test_staff_table_service.py`
- Create: `backend/tests/api/test_staff_tables.py`

**Interfaces:**
- Produces `reconcile_stale_table_orders(db, now) -> None`.
- Produces `list_staff_tables(db, current_user, now=None) -> StaffTablesOverviewResponse`.
- Produces `get_staff_table(db, current_user, table_id, now=None) -> StaffTableDetailResponse`.
- Exposes `GET /api/staff/tables` and `GET /api/staff/tables/{table_id}`.

- [ ] **Step 1: Write failing authorization, aggregation, throttle, and fallback tests**

Create `backend/tests/api/test_staff_tables.py` as an executable test module, including its own helpers rather than referring to private helpers in another test file:

```python
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
        tables.append({"id": str(TABLE_2_ID), "title": "Stol 2", "hallId": str(HALL_ID)})
    return alipos_api.HallsTablesSnapshot(
        payload={
            "halls": [{
                "id": str(HALL_ID),
                "title": "Asosiy zal",
                "servicePercent": 10,
            }],
            "tables": tables,
        },
        stale=stale,
        last_success_at=last_success_at
        or datetime.datetime.now(datetime.UTC),
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
    attempted_at: datetime.datetime | None = None,
    checked_at: datetime.datetime | None = None,
) -> Order:
    order = Order(
        user_id=customer.telegram_id,
        items=[{
            "id": "somsa",
            "name": "Classic Somsa",
            "quantity": 1,
            "price": 18000,
            "modifications": [],
        }],
        items_cost=18000,
        total_amount=total,
        delivery_fee=0,
        payment_method=payment_method,
        payment_status=payment_status,
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
async def test_customer_is_denied_but_staff_and_admin_can_list_tables(client, db_session):
    customer = await create_user(db_session, 8101, "customer")
    staff = await create_user(db_session, 8102, "staff")
    admin = await create_user(db_session, 8103, "admin")
    directory = AsyncMock(return_value=directory_snapshot())

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=directory,
    ):
        denied = await client.get("/api/staff/tables", headers=auth_headers(customer))
        allowed_staff = await client.get("/api/staff/tables", headers=auth_headers(staff))
        allowed_admin = await client.get("/api/staff/tables", headers=auth_headers(admin))

    assert denied.status_code == 403
    assert allowed_staff.status_code == 200
    assert allowed_admin.status_code == 200
    assert directory.await_count == 2


@pytest.mark.asyncio
async def test_overview_returns_all_tables_and_aggregates_only_synced_orders(client, db_session):
    staff = await create_user(db_session, 8110, "staff")
    customer = await create_user(db_session, 8111, "customer")
    await create_table_order(db_session, customer, sync="synced", total=19800)
    await create_table_order(db_session, customer, sync="sending", total=22000)

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=directory_snapshot(two_tables=True)),
    ), patch(
        "app.services.staff_table_service.alipos_api.get_order_status",
        new=AsyncMock(return_value={"status": "NEW", "updatedAt": "2026-07-15T09:00:00Z"}),
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
    customer = await create_user(
        db_session, 8121, "customer", phone="+998901112233"
    )
    order = await create_table_order(db_session, customer, sync="synced", total=19800)

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=directory_snapshot()),
    ), patch(
        "app.services.staff_table_service.alipos_api.get_order_status",
        new=AsyncMock(return_value={"status": "NEW", "updatedAt": "2026-07-15T09:00:00Z"}),
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
async def test_no_directory_and_no_cache_returns_503_before_status_reads(client, db_session):
    staff = await create_user(db_session, 8130, "staff")
    customer = await create_user(db_session, 8131, "customer")
    await create_table_order(db_session, customer, sync="synced", total=19800)
    status_read = AsyncMock()
    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(side_effect=alipos_api.HallsTablesUnavailable()),
    ), patch(
        "app.services.staff_table_service.alipos_api.get_order_status",
        new=status_read,
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
```

Add a separate empty-directory test with no orders:

```python
@pytest.mark.asyncio
async def test_valid_empty_directory_returns_200_without_fabricating_local_tables(client, db_session):
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
async def test_partial_status_failure_keeps_cached_order_and_removes_new_terminal(client, db_session):
    staff = await create_user(db_session, 8160, "staff")
    customer = await create_user(db_session, 8161, "customer")
    failed = await create_table_order(db_session, customer, sync="synced", total=19800)
    terminal = await create_table_order(db_session, customer, sync="synced", total=22000)

    async def status_side_effect(alipos_id: str) -> dict:
        if alipos_id == str(failed.alipos_order_id):
            raise RuntimeError("provider unavailable")
        assert alipos_id == str(terminal.alipos_order_id)
        return {"status": "DELIVERED", "updatedAt": "2026-07-15T09:00:00Z"}

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=directory_snapshot()),
    ), patch(
        "app.services.staff_table_service.alipos_api.get_order_status",
        new=AsyncMock(side_effect=status_side_effect),
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

    with patch(
        "app.services.staff_table_service.alipos_api.get_halls_and_tables_snapshot",
        new=AsyncMock(return_value=directory_snapshot()),
    ), patch(
        "app.services.staff_table_service.alipos_api.get_order_status",
        new=status_read,
    ):
        response = await client.get("/api/staff/tables", headers=auth_headers(staff))

    assert response.status_code == 200
    assert response.json()["data"]["freshness"]["order_status_stale"] is True
    status_read.assert_not_awaited()
```

Extend the imports in `backend/tests/test_staff_table_service.py` with `asyncio`, `logging`, `from unittest.mock import AsyncMock, patch`, `pytest`, `select`, `text`, `from sqlalchemy.engine import make_url`, `async_sessionmaker`, `create_async_engine`, `NullPool`, `settings`, `Base`, `User`, and `reconcile_stale_table_orders`. Then append this PostgreSQL-backed cross-worker test. It creates and drops only its own UUID-suffixed database, so the proof runs under the repository's normal `restaurant_db` configuration without committing into that database:

```python
@pytest.mark.asyncio
async def test_reconcile_atomically_throttles_caps_concurrency_and_logs_safe_counts(caplog):
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
                "items": [{
                    "id": "somsa",
                    "name": "Somsa",
                    "quantity": 1,
                    "price": 100,
                    "modifications": [],
                }],
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
            setup.add(User(
                telegram_id=telegram_id,
                first_name="Concurrency",
                last_name=None,
                username=None,
                phone_number=None,
                role="customer",
            ))
            setup.add_all([
                persisted_order(alipos_order_id=provider_id)
                for provider_id in stale_provider_ids
            ])
            setup.add(persisted_order(
                alipos_order_id=fresh_provider_id,
                alipos_status_check_attempted_at=now_naive,
                alipos_status_checked_at=now_naive,
            ))
            setup.add(persisted_order(
                alipos_order_id=uuid.uuid4(),
                table_id=None,
                table_title=None,
            ))
            setup.add(persisted_order(
                alipos_order_id=uuid.uuid4(),
                payment_method="rahmat",
                payment_status="pending",
            ))
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
            rows = list((await verify.scalars(
                select(Order).where(Order.user_id == telegram_id)
            )).all())
        by_provider = {row.alipos_order_id: row for row in rows}
        for provider_id in stale_provider_ids[:-1]:
            assert by_provider[provider_id].alipos_status_check_attempted_at is not None
            assert by_provider[provider_id].alipos_status_checked_at is not None
            assert by_provider[provider_id].order_number == f"N-{str(provider_id)[-4:]}"
        assert by_provider[failed_provider_id].alipos_status_check_attempted_at is not None
        assert by_provider[failed_provider_id].alipos_status_checked_at is None
        assert by_provider[fresh_provider_id].alipos_status_check_attempted_at == now_naive
        hidden = [row for row in rows if row.table_id is None]
        unpaid = [row for row in rows if row.payment_method == "rahmat"]
        assert hidden[0].alipos_status_check_attempted_at is None
        assert unpaid[0].alipos_status_check_attempted_at is None
        reconcile_logs = [
            record.getMessage() for record in caplog.records
            if record.name == "uvicorn.error"
            and record.getMessage().startswith("staff_table_status_reconcile ")
        ]
        assert len(reconcile_logs) == 1
        assert "claimed=6 succeeded=5 failed=1" in reconcile_logs[0]
        assert all(str(provider_id) not in reconcile_logs[0] for provider_id in stale_provider_ids)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin_engine.connect() as admin:
                await admin.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ), {"database": test_database})
                await admin.execute(text(f'DROP DATABASE IF EXISTS "{test_database}"'))
        finally:
            await admin_engine.dispose()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_staff_table_service.py tests/api/test_staff_tables.py -q
```

Expected: FAIL because async loading/reconciliation and routes do not exist.

- [ ] **Step 3: Implement durable atomic claims and bounded provider reads**

Add these imports and functions to `staff_table_service.py`:

```python
import asyncio
import logging
import time

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services import alipos_api
from app.services.order_status_service import apply_alipos_status_update_for_order
from app.services.permissions import require_staff
from app.services.table_access_service import parse_table_directory

STATUS_ATTEMPT_TTL = datetime.timedelta(seconds=30)
STATUS_STALE_AFTER = datetime.timedelta(seconds=60)
STATUS_READ_CONCURRENCY = 5

# The production image runs Uvicorn's configured logger at INFO. A normal
# app.* logger would inherit an unconfigured/root WARNING path and hide this event.
logger = logging.getLogger("uvicorn.error")


class StaffTableDirectoryUnavailable(RuntimeError):
    pass


class StaffTableNotFound(LookupError):
    pass


def _naive_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(datetime.UTC).replace(tzinfo=None)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


async def _claim_stale_status_orders(
    db: AsyncSession,
    now: datetime.datetime,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    cutoff = _naive_utc(now - STATUS_ATTEMPT_TTL)
    statement = (
        update(Order)
        .where(
            Order.discriminator == "inplace",
            Order.table_id.is_not(None),
            Order.alipos_sync_status == "synced",
            Order.alipos_order_id.is_not(None),
            Order.status.not_in(TERMINAL_TABLE_STATUSES | PRE_ORDER_STATUSES),
            or_(
                Order.payment_method == "cash",
                Order.payment_status == "paid",
            ),
            or_(
                Order.alipos_status_check_attempted_at.is_(None),
                Order.alipos_status_check_attempted_at <= cutoff,
            ),
        )
        .values(alipos_status_check_attempted_at=_naive_utc(now))
        .returning(Order.id, Order.alipos_order_id)
        .execution_options(synchronize_session=False)
    )
    rows = list((await db.execute(statement)).all())
    await db.commit()
    return [(row.id, row.alipos_order_id) for row in rows if row.alipos_order_id]


async def reconcile_stale_table_orders(
    db: AsyncSession,
    now: datetime.datetime,
) -> None:
    claimed = await _claim_stale_status_orders(db, now)
    started_at = time.monotonic()
    semaphore = asyncio.Semaphore(STATUS_READ_CONCURRENCY)

    async def read_status(local_id: uuid.UUID, alipos_id: uuid.UUID):
        async with semaphore:
            try:
                payload = await alipos_api.get_order_status(str(alipos_id))
            except Exception:
                return local_id, None, None, None
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("status"), str)
                or not payload["status"].strip()
            ):
                return local_id, None, None, None
            raw_order_number = payload.get("orderNumber")
            order_number = (
                str(raw_order_number).strip()
                if isinstance(raw_order_number, (str, int))
                and str(raw_order_number).strip()
                else None
            )
            return local_id, payload["status"].strip(), order_number, _utcnow()

    results = await asyncio.gather(*(read_status(*row) for row in claimed))
    succeeded = 0
    for local_id, status_value, order_number, completed_at in results:
        if status_value is None or completed_at is None:
            continue
        order = await db.get(Order, local_id)
        if order is None:
            continue
        await apply_alipos_status_update_for_order(
            db,
            order,
            status_value,
            order_number,
        )
        order.alipos_status_checked_at = _naive_utc(completed_at)
        succeeded += 1
    await db.commit()
    if claimed:
        logger.info(
            "staff_table_status_reconcile claimed=%d succeeded=%d failed=%d duration_ms=%d",
            len(claimed),
            succeeded,
            len(claimed) - succeeded,
            round((time.monotonic() - started_at) * 1000),
        )
```

Do not hold a database transaction open during network reads. The atomic `UPDATE ... RETURNING` is the cross-worker throttle claim. The verified known-order response supplies `orderNumber`; normalize it to a non-empty string and pass it through the existing status-update service. The one structured batch log contains counts and duration only—never local/provider order IDs, payloads, tokens, or customer data—and is the release-time provider-read signal used in Task 10.

- [ ] **Step 4: Implement workspace loading and routes**

Add the exact shared loader below. Authorization and a usable directory happen before any status claim, so a customer or no-cache directory failure cannot consume provider reads or advance attempt timestamps. The post-reconciliation `populate_existing` query is essential: it removes orders that just became terminal and refreshes failed-attempt timestamps before freshness is computed.

```python
@dataclass(frozen=True)
class WorkspaceData:
    directory: list[TableDirectoryEntry]
    orders: list[Order]
    freshness: StaffTablesFreshnessResponse


def _as_aware_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def _status_freshness(
    orders: list[Order],
    now: datetime.datetime,
) -> tuple[bool, datetime.datetime | None]:
    synchronized = [
        order for order in orders
        if classify_table_order(order) == "synchronized"
    ]
    now_naive = _naive_utc(now)
    cutoff = now_naive - STATUS_STALE_AFTER
    stale = any(
        order.alipos_status_checked_at is None
        or order.alipos_status_checked_at < cutoff
        or (
            order.alipos_status_check_attempted_at is not None
            and (
                order.alipos_status_checked_at is None
                or order.alipos_status_check_attempted_at
                > order.alipos_status_checked_at
            )
        )
        for order in synchronized
    )
    successes = [
        _as_aware_utc(order.alipos_status_checked_at)
        for order in synchronized
        if order.alipos_status_checked_at is not None
    ]
    return stale, min(successes, default=None)


async def _load_workspace(
    db: AsyncSession,
    current_user: User,
    now: datetime.datetime | None,
) -> WorkspaceData:
    require_staff(current_user)
    resolved_now = _as_aware_utc(now or _utcnow())
    try:
        snapshot = await alipos_api.get_halls_and_tables_snapshot()
    except alipos_api.HallsTablesUnavailable as exc:
        raise StaffTableDirectoryUnavailable() from exc
    directory = parse_table_directory(snapshot.payload)

    await reconcile_stale_table_orders(db, resolved_now)
    statement = (
        select(Order)
        .where(
            Order.discriminator == "inplace",
            Order.table_id.is_not(None),
            Order.status.not_in(TERMINAL_TABLE_STATUSES | PRE_ORDER_STATUSES),
            Order.alipos_sync_status.in_((
                "synced", "queued", "sending", "failed", "unknown",
            )),
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .execution_options(populate_existing=True)
    )
    orders = list((await db.scalars(statement)).all())
    order_status_stale, oldest_success = _status_freshness(
        orders,
        resolved_now,
    )
    freshness = StaffTablesFreshnessResponse(
        generated_at=_utcnow(),
        directory_stale=snapshot.stale,
        directory_last_success_at=_as_aware_utc(snapshot.last_success_at),
        order_status_stale=order_status_stale,
        order_status_oldest_success_at=oldest_success,
    )
    return WorkspaceData(
        directory=directory,
        orders=orders,
        freshness=freshness,
    )
```

Expose:

```python
async def list_staff_tables(
    db: AsyncSession,
    current_user: User,
    now: datetime.datetime | None = None,
) -> StaffTablesOverviewResponse:
    workspace = await _load_workspace(db, current_user, now)
    return build_staff_tables_overview(
        workspace.directory,
        workspace.orders,
        workspace.freshness,
    )


async def get_staff_table(
    db: AsyncSession,
    current_user: User,
    table_id: uuid.UUID,
    now: datetime.datetime | None = None,
) -> StaffTableDetailResponse:
    workspace = await _load_workspace(db, current_user, now)
    detail = build_staff_table_detail(
        table_id,
        workspace.directory,
        workspace.orders,
        workspace.freshness,
    )
    if detail is None:
        raise StaffTableNotFound("Table not found")
    return detail
```

Add router imports and endpoints to `backend/app/routers/staff.py` before `/orders/{order_id}`:

```python
from fastapi import HTTPException, status

from app.services import staff_table_service


@router.get("/tables")
async def list_tables(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    try:
        result = await staff_table_service.list_staff_tables(db, current_user)
    except staff_table_service.StaffTableDirectoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Table directory is temporarily unavailable",
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(mode="json"))


@router.get("/tables/{table_id}")
async def get_table(
    table_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    try:
        result = await staff_table_service.get_staff_table(
            db,
            current_user,
            table_id,
        )
    except staff_table_service.StaffTableDirectoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Table directory is temporarily unavailable",
        ) from exc
    except staff_table_service.StaffTableNotFound as exc:
        raise HTTPException(status_code=404, detail="Table not found") from exc
    return ApiResponse(success=True, data=result.model_dump(mode="json"))
```

- [ ] **Step 5: Run backend regression tests and commit**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_staff_table_service.py tests/api/test_staff_tables.py tests/api/test_staff_delivery.py tests/api/test_tables.py tests/api/test_orders_status.py -q
```

Expected: PASS.

```bash
git add backend/app/services/staff_table_service.py backend/app/routers/staff.py backend/tests/test_staff_table_service.py backend/tests/api/test_staff_tables.py
git commit -m "feat: expose staff table inspection api"
```

---

### Task 5: Add the typed frontend table-inspection client

**Files:**
- Create: `frontend/src/types/staffTables.ts`
- Create: `frontend/src/services/staffTablesApi.ts`
- Create: `frontend/src/services/staffTablesApi.test.ts`

**Interfaces:**
- Produces `getStaffTables() -> AxiosResponse<ApiResponse<StaffTablesOverview>>`.
- Produces `getStaffTable(tableId) -> AxiosResponse<ApiResponse<StaffTableDetail>>`.
- Produces TypeScript contracts matching Task 3 exactly.

- [ ] **Step 1: Write failing API client tests**

Create `frontend/src/services/staffTablesApi.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('./api', () => ({ default: apiMocks }));

import { getStaffTable, getStaffTables } from './staffTablesApi';

describe('staffTablesApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads the complete table overview', async () => {
    apiMocks.get.mockResolvedValue({ data: { success: true, data: { halls: [] } } });
    await getStaffTables();
    expect(apiMocks.get).toHaveBeenCalledWith('/staff/tables');
  });

  it('loads one table using an encoded id', async () => {
    apiMocks.get.mockResolvedValue({ data: { success: true, data: {} } });
    await getStaffTable('table/id');
    expect(apiMocks.get).toHaveBeenCalledWith('/staff/tables/table%2Fid');
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && npm test -- src/services/staffTablesApi.test.ts
```

Expected: FAIL because the client module does not exist.

- [ ] **Step 3: Add exact TypeScript response types**

Create `frontend/src/types/staffTables.ts`:

```typescript
export type StaffTableSyncState = 'synchronized' | 'processing' | 'attention';
export type StaffTableSyncLabel =
  | 'synchronized'
  | 'processing'
  | 'not_synchronized'
  | 'verify_in_pos';

export interface StaffTableModifier {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
}

export interface StaffTableOrderItem {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
  modifications: StaffTableModifier[];
}

export interface StaffTableItem extends StaffTableOrderItem {
  line_total: number;
}

export interface StaffTableOrder {
  id: string;
  order_number: string | null;
  created_at: string;
  status: string;
  sync_state: StaffTableSyncState;
  sync_label: StaffTableSyncLabel;
  payment_method: 'cash' | 'online';
  payment_status: 'paid' | null;
  items: StaffTableOrderItem[];
  items_cost: number;
  service_amount: number;
  total_amount: number;
}

export interface StaffTableSummary {
  table_id: string;
  table_title: string;
  hall_id: string | null;
  hall_title: string | null;
  service_percent: number;
  is_listed: boolean;
  synchronized_order_count: number;
  processing_order_count: number;
  attention_order_count: number;
  combined_item_count: number;
  combined_line_count: number;
  combined_items: StaffTableItem[];
  items_cost: number;
  service_amount: number;
  total_amount: number;
}

export interface StaffHall {
  hall_id: string | null;
  hall_title: string | null;
  service_percent: number | null;
  is_listed: boolean;
  tables: StaffTableSummary[];
}

export interface StaffTablesFreshness {
  generated_at: string;
  directory_stale: boolean;
  directory_last_success_at: string;
  order_status_stale: boolean;
  order_status_oldest_success_at: string | null;
}

export interface StaffTablesOverview {
  freshness: StaffTablesFreshness;
  halls: StaffHall[];
}

export interface StaffTableDetail {
  freshness: StaffTablesFreshness;
  table: StaffTableSummary;
  orders: StaffTableOrder[];
}
```

- [ ] **Step 4: Implement the client and run tests**

Create `frontend/src/services/staffTablesApi.ts`:

```typescript
import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse } from '../types/api';
import type { StaffTableDetail, StaffTablesOverview } from '../types/staffTables';

export const getStaffTables = (): Promise<AxiosResponse<ApiResponse<StaffTablesOverview>>> =>
  api.get('/staff/tables');

export const getStaffTable = (
  tableId: string,
): Promise<AxiosResponse<ApiResponse<StaffTableDetail>>> =>
  api.get(`/staff/tables/${encodeURIComponent(tableId)}`);
```

Run:

```bash
cd frontend && npm test -- src/services/staffTablesApi.test.ts && npm run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit the typed client**

```bash
git add frontend/src/types/staffTables.ts frontend/src/services/staffTablesApi.ts frontend/src/services/staffTablesApi.test.ts
git commit -m "feat: add staff table api client"
```

---

### Task 6: Extract a reusable interactive/browse menu catalog

**Files:**
- Create: `frontend/src/components/menu/MenuCatalog.tsx`
- Create: `frontend/src/components/menu/MenuCatalog.test.tsx`
- Create: `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.tsx:1-507`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/uz.json`

**Interfaces:**
- Produces `<MenuCatalog mode="interactive" | "browse" ... />`.
- Interactive mode receives quantities and add/remove callbacks.
- Browse mode renders no cart-related controls and imports no Zustand store.

- [ ] **Step 1: Write failing browse and interactive component tests**

Create `frontend/src/components/menu/MenuCatalog.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import MenuCatalog from './MenuCatalog';

const menu = {
  categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
  items: [
    { id: 'classic', categoryId: 'somsa', name: 'Classic Somsa', description: 'Beef and onion', price: 18000, sortOrder: 0, available: true, availableCount: 1, images: [{ url: '/classic.jpg' }] },
    { id: 'sold', categoryId: 'somsa', name: 'Fish Somsa', description: null, price: 24000, sortOrder: 1, available: false, availableCount: 0 },
  ],
};

const labels = {
  soldOut: 'Sold out',
  add: 'Add',
  remove: 'Remove',
  limit: 'Available quantity is already in the cart',
  empty: 'No menu items',
};

describe('MenuCatalog', () => {
  it('renders browse mode without ordering controls', () => {
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="browse"
        labels={labels}
      />,
    );

    expect(screen.getAllByText('Somsa')).toHaveLength(2);
    expect(screen.getByText('Beef and onion')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Classic Somsa' })).toHaveAttribute('src', '/classic.jpg');
    expect(screen.getByText('18,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('Sold out')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/cart|checkout|table context/i)).not.toBeInTheDocument();
  });

  it('keeps customer interactive add behavior', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ classic: 0 }}
        onAdd={onAdd}
        onRemove={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /classic somsa.*add/i }));
    expect(onAdd).toHaveBeenCalledWith(menu.items[0]);
  });

  it('keeps remove behavior and disables additions at the live limit', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ classic: 1 }}
        onAdd={vi.fn()}
        onRemove={onRemove}
      />,
    );

    expect(screen.getByRole('button', { name: labels.limit })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /classic somsa.*remove/i }));
    expect(onRemove).toHaveBeenCalledWith('classic');
  });

  it('renders the localized empty state', () => {
    render(
      <MenuCatalog
        menu={{ categories: [], items: [] }}
        language="en"
        mode="browse"
        labels={labels}
      />,
    );
    expect(screen.getByText('No menu items')).toBeInTheDocument();
  });
});
```

Create `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx` as a route-level regression test for the extraction:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuCatalogProps } from '../../components/menu/MenuCatalog';
import ArtisanMenuPage from './ArtisanMenuPage';

const menuState = vi.hoisted(() => ({
  menu: {
    categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
    items: [{
      id: 'classic',
      categoryId: 'somsa',
      name: 'Classic Somsa',
      description: 'Beef and onion',
      price: 18000,
      sortOrder: 0,
      available: true,
      availableCount: 5,
      images: [{ url: '/classic.jpg' }],
    }],
  },
  loading: false,
  error: null as string | null,
  fetchMenu: vi.fn(async () => undefined),
  retry: vi.fn(async () => undefined),
}));

const cartState = vi.hoisted(() => ({
  items: [{
    id: 'classic',
    categoryId: 'somsa',
    name: 'Classic Somsa',
    description: 'Beef and onion',
    price: 18000,
    sortOrder: 0,
    available: true,
    availableCount: 5,
    images: [{ url: '/classic.jpg' }],
    quantity: 1,
  }],
  addItem: vi.fn(),
  removeItem: vi.fn(),
  updateQuantity: vi.fn(),
  getItemCount: vi.fn(() => 1),
  getTotal: vi.fn(() => 18000),
  reconcileAvailability: vi.fn(() => ({ removed: 0, reduced: 0 })),
}));

const tableState = vi.hoisted(() => ({
  context: {
    tableTitle: 'Table 2',
    hallTitle: 'Main hall',
    servicePercent: 10,
    accessToken: 'signed-table-token',
  },
  resolveCode: vi.fn(async () => undefined),
  isResolving: false,
  error: null as string | null,
  clearError: vi.fn(),
}));

const authState = vi.hoisted(() => ({ isAuthenticated: false }));
const apiMocks = vi.hoisted(() => ({ getMe: vi.fn() }));

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, fallback?: string) => key === 'menu.checkout' ? 'Checkout' : fallback ?? key,
      i18n: { language: 'en' },
    }),
  };
});

vi.mock('../../stores/menuStore', () => ({
  useMenuStore: (selector: (state: typeof menuState) => unknown) => selector(menuState),
}));
vi.mock('../../stores/cartStore', () => ({
  useCartStore: (selector: (state: typeof cartState) => unknown) => selector(cartState),
}));
vi.mock('../../stores/tableOrderStore', () => ({
  useTableOrderStore: (selector: (state: typeof tableState) => unknown) => selector(tableState),
}));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../services/api', () => apiMocks);

vi.mock('../../components/menu/MenuCatalog', () => ({
  default: (props: MenuCatalogProps) => {
    if (props.mode !== 'interactive') return <div>browse catalog</div>;
    const item = props.menu.items[0];
    return (
      <div>
        <span>interactive catalog</span>
        <button type="button" onClick={() => props.onAdd(item)}>Catalog add</button>
        <button type="button" onClick={() => props.onRemove(item.id)}>Catalog remove</button>
      </div>
    );
  },
}));

describe('ArtisanMenuPage catalog extraction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('preserves loading, table context, cart wiring, and checkout presentation', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ArtisanMenuPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('interactive catalog')).toBeInTheDocument();
    expect(screen.getByText('Table 2')).toBeInTheDocument();
    expect(screen.getByText('18,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('Checkout')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Catalog add' }));
    expect(cartState.addItem).toHaveBeenCalledWith(menuState.menu.items[0]);
    await user.click(screen.getByRole('button', { name: 'Catalog remove' }));
    expect(cartState.removeItem).toHaveBeenCalledWith('classic');
    expect(menuState.fetchMenu).toHaveBeenCalledTimes(1);
    expect(apiMocks.getMe).not.toHaveBeenCalled();
  });
});
```

The mock imports and uses the public discriminated `MenuCatalogProps`; do not weaken it to `any`. This complements the component tests by protecting the customer page responsibilities that stay outside the shared catalog.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && npm test -- src/components/menu/MenuCatalog.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Move catalog-only presentation behind an explicit mode**

Create `MenuCatalog.tsx` by moving `GroupedCategory`, category icons/assets, `ProductCard`, category grouping, scroll spy, category rail, and product-list markup out of `ArtisanMenuPage.tsx`. Import `useEffect`, `useMemo`, `useRef`, and `useState`, plus `COLORS`, `FONTS`, `Icon`, `formatPrice`, and the five existing category assets. Sort copies (`[...menu.categories]`, `[...menu.items]`) so this shared component never mutates the Zustand menu object.

Use this public prop contract:

```tsx
import type { MenuData, MenuItem } from '../../types/api';

export interface MenuCatalogLabels {
  soldOut: string;
  add: string;
  remove: string;
  limit: string;
  empty: string;
}

interface MenuCatalogBaseProps {
  menu: MenuData;
  language: string;
  labels: MenuCatalogLabels;
  notice?: string | null;
}

export type MenuCatalogProps = MenuCatalogBaseProps & (
  | {
      mode: 'browse';
      quantities?: never;
      onAdd?: never;
      onRemove?: never;
    }
  | {
      mode: 'interactive';
      quantities: Record<string, number>;
      onAdd: (item: MenuItem) => void;
      onRemove: (itemId: string) => void;
    }
);
```

Keep the existing card image, alt text, description, formatted price, sold-out opacity, category rail, and scroll-spy JSX unchanged. Enforce the discriminated mode at the product-card boundary:

```tsx
const available = product.available !== false;
const interactive = props.mode === 'interactive';
const quantity = interactive ? props.quantities[product.id] ?? 0 : 0;
const atLimit = product.availableCount !== null && quantity >= product.availableCount;

{!available ? (
  <span>{props.labels.soldOut}</span>
) : interactive && quantity > 0 ? (
  <div>
    <button
      type="button"
      aria-label={`${product.name} ${props.labels.remove}`}
      onClick={() => props.onRemove(product.id)}
    >
      <Icon name="remove" size={16} />
    </button>
    <span>{quantity}</span>
    <button
      type="button"
      aria-label={atLimit ? props.labels.limit : `${product.name} ${props.labels.add}`}
      onClick={() => props.onAdd(product)}
      disabled={atLimit}
    >
      <Icon name="add" size={16} />
    </button>
  </div>
) : interactive ? (
  <button
    type="button"
    aria-label={`${product.name} ${props.labels.add}`}
    onClick={() => props.onAdd(product)}
  >
    <Icon name="add" />
  </button>
) : null}
```

When no category contains an item, render `<p>{props.labels.empty}</p>`. Do not import `useCartStore`, `useTableOrderStore`, `useAuthStore`, `useMenuStore`, or navigation APIs in `MenuCatalog.tsx`; the union must make browse-mode cart props a TypeScript error.

- [ ] **Step 4: Rewire the customer page to interactive mode**

Keep data loading, profile/table context, cart store operations, checkout bar, and table-code sheet in `ArtisanMenuPage.tsx`. Build a quantity map and pass handlers:

```tsx
const quantities = useMemo(
  () => Object.fromEntries(cartItems.map((item) => [item.id, item.quantity])),
  [cartItems],
);

<MenuCatalog
  menu={menu}
  language={i18n.language}
  mode="interactive"
  labels={{
    soldOut: t('menu.sold_out', "Sotuvda yo'q"),
    add: t('menu.add', 'Add'),
    remove: t('menu.remove', 'Remove'),
    limit: t('menu.limit', 'Available quantity is already in the cart'),
    empty: t('menu.empty', 'No menu items'),
  }}
  quantities={quantities}
  onAdd={handleAdd}
  onRemove={handleRemove}
  notice={cartNotice}
/>
```

Delete the moved private catalog definitions, category state, grouping memo, refs, scroll listener, and category-click handler from the page; do not duplicate them. Keep `TableContextBar`, `TableCodeSheet`, cart reconciliation/notice, and the sticky checkout bar in the customer page. Add these exact values to the existing `menu` object in each locale:

```json
// en.json
"add": "Add",
"remove": "Remove",
"limit": "Available quantity is already in the cart",
"empty": "No menu items",
"retry": "Retry"

// ru.json
"add": "Добавить",
"remove": "Уменьшить",
"limit": "Всё доступное количество уже в корзине",
"empty": "В меню пока нет позиций",
"retry": "Повторить"

// uz.json
"add": "Qo‘shish",
"remove": "Kamaytirish",
"limit": "Mavjud miqdorning barchasi savatda",
"empty": "Menyuda hozircha mahsulot yo‘q",
"retry": "Qayta urinish"
```

These are insertion fragments, not standalone JSON documents; preserve commas required by each surrounding object.

- [ ] **Step 5: Run customer regressions and commit**

Run:

```bash
cd frontend && npm test -- src/components/menu/MenuCatalog.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx src/stores/__tests__/cartStore.test.ts src/stores/__tests__/menuStore.test.ts src/App.test.tsx && npm run typecheck
cd .. && ! rg -n "useCartStore|useTableOrderStore|useAuthStore|useMenuStore|useNavigate" frontend/src/components/menu/MenuCatalog.tsx
```

Expected: PASS.

```bash
git add frontend/src/components/menu/MenuCatalog.tsx frontend/src/components/menu/MenuCatalog.test.tsx frontend/src/pages/artisan/ArtisanMenuPage.tsx frontend/src/pages/artisan/ArtisanMenuPage.test.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
git commit -m "refactor: share customer menu catalog"
```

---

### Task 7: Add visibility-aware polling

**Files:**
- Create: `frontend/src/hooks/useVisiblePolling.ts`
- Create: `frontend/src/hooks/useVisiblePolling.test.tsx`

**Interfaces:**
- Produces `useVisiblePolling<T>(load, intervalMs, requestKey) -> {data, loading, error, refresh}`.
- Starts immediately, polls every 15 seconds only while visible, preserves cached data and the original error object on failure, reloads immediately when `requestKey` changes, ignores superseded responses, deduplicates overlapping refreshes for one key, and cleans up timers/listeners.

- [ ] **Step 1: Write failing timer and visibility tests**

Create `frontend/src/hooks/useVisiblePolling.test.tsx` with a small harness:

```tsx
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useVisiblePolling } from './useVisiblePolling';

const setVisibility = (value: DocumentVisibilityState) => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value,
  });
};

const flushPromises = async () => {
  await act(async () => { await Promise.resolve(); });
};

describe('useVisiblePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility('visible');
  });
  afterEach(() => {
    setVisibility('visible');
    vi.useRealTimers();
  });

  it('loads immediately and polls every 15 seconds', async () => {
    const load = vi.fn().mockResolvedValue({ value: 1 });
    const { result, unmount } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );

    await flushPromises();
    expect(result.current.data).toEqual({ value: 1 });
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(load).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('stops while hidden and refreshes when visible again', async () => {
    const load = vi.fn().mockResolvedValue({ value: 1 });
    setVisibility('hidden');
    renderHook(() => useVisiblePolling(load, 15_000, 'overview'));
    await flushPromises();

    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(load).toHaveBeenCalledTimes(1);

    setVisibility('visible');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await flushPromises();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(load).toHaveBeenCalledTimes(3);

    setVisibility('hidden');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(load).toHaveBeenCalledTimes(3);

    setVisibility('visible');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await flushPromises();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(load).toHaveBeenCalledTimes(5);
  });

  it('keeps prior data when a refresh fails', async () => {
    const failure = { response: { status: 503 } };
    const load = vi.fn()
      .mockResolvedValueOnce({ value: 1 })
      .mockRejectedValueOnce(failure);
    const { result } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );
    await flushPromises();

    await act(async () => { await result.current.refresh(); });
    expect(result.current.data).toEqual({ value: 1 });
    expect(result.current.error).toBe(failure);
  });

  it('reloads on key change and ignores a superseded response', async () => {
    let resolveFirst!: (value: { value: string }) => void;
    const first = new Promise<{ value: string }>((resolve) => { resolveFirst = resolve; });
    const loadFirst = vi.fn(() => first);
    const loadSecond = vi.fn().mockResolvedValue({ value: 'second' });
    const { result, rerender } = renderHook(
      ({ tableId }) => useVisiblePolling(
        tableId === 'one' ? loadFirst : loadSecond,
        15_000,
        tableId,
      ),
      { initialProps: { tableId: 'one' } },
    );

    rerender({ tableId: 'two' });
    await flushPromises();
    expect(result.current.data).toEqual({ value: 'second' });

    resolveFirst({ value: 'first' });
    await flushPromises();
    expect(result.current.data).toEqual({ value: 'second' });
  });
});
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
cd frontend && npm test -- src/hooks/useVisiblePolling.test.tsx
```

Expected: FAIL because the hook does not exist.

- [ ] **Step 3: Implement one timer/listener owner**

Create `frontend/src/hooks/useVisiblePolling.ts`:

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';

export function useVisiblePolling<T>(
  load: () => Promise<T>,
  intervalMs: number,
  requestKey: unknown,
) {
  const loadRef = useRef(load);
  loadRef.current = load;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown | null>(null);
  const mountedRef = useRef(false);
  const generationRef = useRef(0);
  const inFlightRef = useRef<Promise<void> | null>(null);

  const refresh = useCallback(async () => {
    if (inFlightRef.current) return inFlightRef.current;
    const generation = generationRef.current;
    const task = (async () => {
      try {
        const next = await loadRef.current();
        if (!mountedRef.current || generation !== generationRef.current) return;
        setData(next);
        setError(null);
      } catch (cause) {
        if (!mountedRef.current || generation !== generationRef.current) return;
        setError(cause);
      } finally {
        if (mountedRef.current && generation === generationRef.current) {
          setLoading(false);
        }
      }
    })();
    inFlightRef.current = task;
    try {
      await task;
    } finally {
      if (inFlightRef.current === task) inFlightRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    generationRef.current += 1;
    inFlightRef.current = null;
    setData(null);
    setError(null);
    setLoading(true);
    let timer: number | undefined;

    const stop = () => {
      if (timer !== undefined) window.clearInterval(timer);
      timer = undefined;
    };
    const start = () => {
      stop();
      if (document.visibilityState !== 'hidden') {
        timer = window.setInterval(() => { void refresh(); }, intervalMs);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        stop();
      } else {
        void refresh();
        start();
      }
    };

    void refresh();
    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      generationRef.current += 1;
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [intervalMs, refresh, requestKey]);

  useEffect(() => () => {
    mountedRef.current = false;
    generationRef.current += 1;
    inFlightRef.current = null;
  }, []);

  return { data, loading, error, refresh };
}
```

- [ ] **Step 4: Run hook tests and type checking**

Run:

```bash
cd frontend && npm test -- src/hooks/useVisiblePolling.test.tsx && npm run typecheck
```

Expected: PASS with no dangling fake-timer warnings.

- [ ] **Step 5: Commit the polling unit**

```bash
git add frontend/src/hooks/useVisiblePolling.ts frontend/src/hooks/useVisiblePolling.test.tsx
git commit -m "feat: add visibility aware polling"
```

---

### Task 8: Build the Tables workspace, filters, browse menu, routes, and navigation

**Files:**
- Create: `frontend/src/pages/staff/StaffTablesPage.tsx`
- Create: `frontend/src/pages/staff/StaffTablesPage.test.tsx`
- Create: `frontend/src/i18n/staffTablesLocales.test.ts`
- Create: `frontend/src/components/artisan/ArtisanLayout.test.tsx`
- Create: `frontend/src/components/staff/TableWorkspaceToggle.tsx`
- Create: `frontend/src/components/staff/TableInspectionCard.tsx`
- Create: `frontend/src/components/staff/TableHallSection.tsx`
- Create: `frontend/src/staff-tables.css`
- Modify: `frontend/src/App.tsx:1-198`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/staff/StaffLayout.tsx:1-146`
- Modify: `frontend/src/components/staff/StaffLayout.test.tsx`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/uz.json`

**Interfaces:**
- Exposes `/staff/tables` for staff/admin.
- Uses `?view=tables|menu` and `?filter=all|active|attention`.
- Uses `useVisiblePolling(() => getStaffTables().then(response => response.data.data), 15_000, 'staff-tables')`.
- Reuses `MenuCatalog` in browse mode.

- [ ] **Step 1: Write failing route/navigation/workspace tests**

Add mocked `StaffTablesPage` coverage to `App.test.tsx`:

```tsx
vi.mock('./pages/staff/StaffTablesPage', () => ({
  default: () => <div>Staff tables page</div>,
}));

it('lets staff and admin open the staff tables route', () => {
  for (const role of ['staff', 'admin']) {
    cleanup();
    authState.user = { role };
    render(<MemoryRouter initialEntries={['/staff/tables']}><App /></MemoryRouter>);
    expect(screen.getByText('Staff tables page')).toBeInTheDocument();
  }
});

it('routes customers away from staff tables', () => {
  authState.user = { role: 'customer' };
  render(<MemoryRouter initialEntries={['/staff/tables']}><App /></MemoryRouter>);
  expect(screen.getByText('Artisan menu page')).toBeInTheDocument();
});
```

In `StaffLayout.test.tsx`, import `within` and replace the old count assertions with executable order/count checks:

```tsx
const nav = screen.getByRole('navigation', { name: 'Staff navigation' });
expect(within(nav).getAllByRole('link').map(
  (link) => link.querySelector('span:last-child')?.textContent,
)).toEqual([
  'Tables', 'Delivery', 'Profile',
]);

// In the admin test:
const adminNav = screen.getByRole('navigation', { name: 'Admin navigation' });
expect(within(adminNav).getAllByRole('link').map(
  (link) => link.querySelector('span:last-child')?.textContent,
)).toEqual([
  'Admin', 'Tables', 'Delivery', 'Profile',
]);
```

Create `frontend/src/components/artisan/ArtisanLayout.test.tsx` as a regression guard:

```tsx
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ArtisanLayout from './ArtisanLayout';

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { isAuthenticated: boolean }) => unknown) =>
    selector({ isAuthenticated: false }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'nav.menu': 'Menu', 'nav.orders': 'Orders', 'nav.cart': 'Cart', 'nav.profile': 'Profile',
    }[key] ?? key),
  }),
}));

describe('ArtisanLayout customer navigation', () => {
  it('keeps the existing four customer destinations unchanged', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <ArtisanLayout><div>Content</div></ArtisanLayout>
      </MemoryRouter>,
    );
    const links = within(screen.getByRole('navigation')).getAllByRole('link');
    expect(links.map(
      (link) => link.querySelector('span:last-child')?.textContent,
    )).toEqual(['Menu', 'Orders', 'Cart', 'Profile']);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/', '/order', '/checkout', '/profile',
    ]);
  });
});
```

This file does not change customer implementation; it proves staff navigation work did not alter it.

Create `StaffTablesPage.test.tsx` with the following complete test setup and assertions:

```tsx
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StaffTablesPage from './StaffTablesPage';
import type { StaffTableSummary, StaffTablesOverview } from '../../types/staffTables';
import type { MenuData } from '../../types/api';

const apiMocks = vi.hoisted(() => ({ getStaffTables: vi.fn() }));
const menuState = vi.hoisted(() => ({
  menu: {
    categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
    items: [{ id: 'classic', categoryId: 'somsa', name: 'Classic', description: null, price: 18000, sortOrder: 0, available: true, availableCount: null }],
  } as MenuData | null,
  loading: false,
  error: null as string | null,
  fetchMenu: vi.fn().mockResolvedValue(undefined),
  retry: vi.fn().mockResolvedValue(undefined),
}));
const authState = vi.hoisted(() => ({
  user: { role: 'staff' },
  refreshMe: vi.fn().mockResolvedValue({ role: 'staff' }),
}));

vi.mock('../../services/staffTablesApi', () => apiMocks);
vi.mock('../../stores/menuStore', () => ({
  useMenuStore: (selector: (state: typeof menuState) => unknown) => selector(menuState),
}));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../components/menu/MenuCatalog', () => ({
  default: ({ mode }: { mode: string }) => <div>{mode} catalog</div>,
}));
vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, options?: string | { defaultValue?: string; count?: number; percent?: number }) => {
        const value = typeof options === 'string'
          ? options
          : options?.defaultValue ?? _key;
        return value
          .replace('{{count}}', String(typeof options === 'object' ? options.count ?? '' : ''))
          .replace('{{percent}}', String(typeof options === 'object' ? options.percent ?? '' : ''));
      },
      i18n: { language: 'en' },
    }),
  };
});

const freshness = {
  generated_at: '2026-07-15T09:00:00Z',
  directory_stale: false,
  directory_last_success_at: '2026-07-15T09:00:00Z',
  order_status_stale: false,
  order_status_oldest_success_at: '2026-07-15T09:00:00Z',
};
const table = (overrides: Partial<StaffTableSummary> = {}): StaffTableSummary => ({
  table_id: '11111111-1111-4111-8111-111111111111',
  table_title: 'Table 2',
  hall_id: '22222222-2222-4222-8222-222222222222',
  hall_title: 'Main hall',
  service_percent: 10,
  is_listed: true,
  synchronized_order_count: 1,
  processing_order_count: 0,
  attention_order_count: 0,
  combined_item_count: 1,
  combined_line_count: 1,
  combined_items: [{ id: 'somsa', name: 'Somsa', quantity: 1, price: 18000, modifications: [], line_total: 18000 }],
  items_cost: 18000,
  service_amount: 1800,
  total_amount: 19800,
  ...overrides,
});
const overview: StaffTablesOverview = {
  freshness,
  halls: [
    {
      hall_id: '22222222-2222-4222-8222-222222222222',
      hall_title: 'Main hall',
      service_percent: 10,
      is_listed: true,
      tables: [
        table({ table_id: '11111111-1111-4111-8111-111111111110', table_title: 'Table 10', synchronized_order_count: 0, combined_item_count: 0, combined_line_count: 0, combined_items: [], items_cost: 0, service_amount: 0, total_amount: 0 }),
        table({}),
      ],
    },
    {
      hall_id: null,
      hall_title: null,
      service_percent: null,
      is_listed: false,
      tables: [table({ table_id: '99999999-9999-4999-8999-999999999999', table_title: 'Removed 9', is_listed: false, synchronized_order_count: 0, attention_order_count: 1, combined_item_count: 0, combined_line_count: 0, combined_items: [], items_cost: 0, service_amount: 0, total_amount: 0 })],
    },
  ],
};

function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}

function renderPage(entry = '/staff/tables') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/staff/tables" element={<><StaffTablesPage /><LocationProbe /></>} />
        <Route path="/" element={<div>Role home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('StaffTablesPage', () => {
  afterEach(() => vi.restoreAllMocks());

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    menuState.error = null;
    menuState.menu = {
      categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
      items: [{ id: 'classic', categoryId: 'somsa', name: 'Classic', description: null, price: 18000, sortOrder: 0, available: true, availableCount: null }],
    };
    apiMocks.getStaffTables.mockResolvedValue({ data: { success: true, data: overview } });
  });

  it('renders every table, natural order, neutral copy, and the unlisted group', async () => {
    renderPage();
    expect(await screen.findByText('No mini-app orders')).toBeInTheDocument();
    expect(screen.getByText('Unlisted tables')).toBeInTheDocument();
    const cards = screen.getAllByRole('link').filter((link) =>
      link.getAttribute('href')?.startsWith('/staff/tables/'),
    );
    expect(cards.map((card) => within(card).getByRole('heading').textContent)).toEqual([
      'Table 2', 'Table 10', 'Removed 9',
    ]);
  });

  it('defines With orders as any visible state and preserves query keys', async () => {
    const user = userEvent.setup();
    renderPage('/staff/tables?view=tables');
    await screen.findByText('Table 2');
    await user.click(screen.getByRole('button', { name: 'With orders' }));
    expect(screen.queryByText('Table 10')).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('view=tables');
    expect(screen.getByTestId('location')).toHaveTextContent('filter=active');
    await user.click(screen.getByRole('button', { name: 'Attention' }));
    expect(screen.getByText('Removed 9')).toBeInTheDocument();
    expect(screen.queryByText('Table 2')).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('filter=attention');
  });

  it('keeps cached cards on refresh failure and announces recovery once', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.getStaffTables
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } });
    renderPage();
    await screen.findByText('Table 2');
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect((await screen.findAllByText('Could not refresh. Showing cached data.')).length).toBeGreaterThan(0);
    expect(consoleError).toHaveBeenCalledWith(
      'staff_tables_workspace_load_failed',
      { status: 503 },
    );
    expect(screen.getByText('Table 2')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByText('Data is up to date again.')).toBeInTheDocument();
  });

  it('renders blocking retry for the first failure and a distinct empty directory', async () => {
    const user = userEvent.setup();
    apiMocks.getStaffTables
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } });
    const view = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Table 2')).toBeInTheDocument();
    view.unmount();

    apiMocks.getStaffTables.mockResolvedValue({
      data: { success: true, data: { freshness, halls: [] } },
    });
    renderPage();
    expect(await screen.findByText('AliPOS returned no tables.')).toBeInTheDocument();
  });

  it('direct-loads menu view, preserves filter, and never supplies order controls', async () => {
    renderPage('/staff/tables?view=menu&filter=attention');
    expect(await screen.findByText('Browse only · Orders cannot be placed here')).toBeInTheDocument();
    expect(screen.getByText('browse catalog')).toBeInTheDocument();
    expect(menuState.fetchMenu).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location')).toHaveTextContent('filter=attention');
    expect(screen.queryByRole('button', { name: /add|remove/i })).not.toBeInTheDocument();
  });

  it('keeps Tables available when menu loading fails and retries only the menu', async () => {
    const user = userEvent.setup();
    menuState.menu = null;
    menuState.error = 'failed';
    renderPage('/staff/tables?view=menu');
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(menuState.retry).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Tables' }));
    expect(await screen.findByText('Table 2')).toBeInTheDocument();
  });

  it('falls back invalid query values to Tables and All', async () => {
    renderPage('/staff/tables?view=invalid&filter=invalid');
    expect(await screen.findByRole('button', { name: 'Tables' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows both stale warnings without hiding cached tables', async () => {
    apiMocks.getStaffTables.mockResolvedValue({
      data: {
        success: true,
        data: {
          ...overview,
          freshness: {
            ...freshness,
            directory_stale: true,
            order_status_stale: true,
          },
        },
      },
    });
    renderPage();
    expect(await screen.findByText(/Table list may be outdated/)).toBeInTheDocument();
    expect(screen.getByText(/Order status may be outdated/)).toBeInTheDocument();
    expect(screen.getByText('Table 2')).toBeInTheDocument();
  });

  it('rehydrates role and leaves the workspace after authoritative 403', async () => {
    apiMocks.getStaffTables.mockRejectedValue({ response: { status: 403 } });
    renderPage();
    expect(await screen.findByText('Role home')).toBeInTheDocument();
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);
  });
});
```

The natural-sort expectation proves that the listed hall produces `Table 2, Table 10`; the unlisted group follows as its own section.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx src/components/staff/StaffLayout.test.tsx src/pages/staff/StaffTablesPage.test.tsx
```

Expected: FAIL because route, nav, components, and page do not exist.

- [ ] **Step 3: Implement reusable workspace presentation**

Use this toggle contract in `TableWorkspaceToggle.tsx`:

```tsx
export default function TableWorkspaceToggle({
  view,
  onChange,
  labels,
}: {
  view: 'tables' | 'menu';
  onChange: (view: 'tables' | 'menu') => void;
  labels: { group: string; tables: string; menu: string };
}) {
  return (
    <div role="group" aria-label={labels.group} className="staff-tables__toggle">
      {(['tables', 'menu'] as const).map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={view === value}
          onClick={() => onChange(value)}
        >
          {labels[value]}
        </button>
      ))}
    </div>
  );
}
```

Implement `TableInspectionCard` as a pure `<Link>` with this data branch; keep all raw IDs in `to`/React keys only, never in visible fallback copy:

```tsx
const activityCount = table.synchronized_order_count
  + table.processing_order_count
  + table.attention_order_count;
const remainingLines = Math.max(
  0,
  table.combined_line_count - table.combined_items.length,
);

<Link
  to={`/staff/tables/${table.table_id}`}
  className={`staff-table-card ${table.synchronized_order_count > 0 ? 'staff-table-card--active' : ''}`}
  aria-label={labels.details(table.table_title)}
>
  <h3>{table.table_title || labels.unknownTable}</h3>
  {activityCount === 0 ? (
    <p className="staff-table-card__neutral">{labels.noOrders}</p>
  ) : (
    <>
      <p>{labels.miniAppOrders(table.synchronized_order_count)}</p>
      <ul>
        {table.combined_items.map((item) => (
          <li key={`${item.id}-${item.price}-${JSON.stringify(item.modifications)}`}>
            {item.name || labels.unknownItem} × {item.quantity}
          </li>
        ))}
      </ul>
      {remainingLines > 0 && <p>{labels.moreItems(remainingLines)}</p>}
      {table.synchronized_order_count > 0 && (
        <strong>{formatPrice(table.total_amount, language)}</strong>
      )}
      <div className="staff-table-card__states">
        {table.processing_order_count > 0 && (
          <span><span aria-hidden="true"><Icon name="hourglass_top" /></span>{labels.processing(table.processing_order_count)}</span>
        )}
        {table.attention_order_count > 0 && (
          <span><span aria-hidden="true"><Icon name="warning" /></span>{labels.attention(table.attention_order_count)}</span>
        )}
      </div>
    </>
  )}
</Link>
```

Define the prop type explicitly: `table: StaffTableSummary`, `language: string`, and a `labels` object containing `details`, `unknownTable`, `unknownItem`, `noOrders`, `miniAppOrders`, `moreItems`, `processing`, and `attention` functions/strings. The card contains no hooks or API calls.

`TableHallSection` renders a semantic heading, optional service percentage, and naturally sorted cards using:

```typescript
const naturalTableSort = (left: StaffTableSummary, right: StaffTableSummary) =>
  left.table_title.localeCompare(right.table_title, undefined, {
    numeric: true,
    sensitivity: 'base',
  });
```

`TableHallSection` receives `hall`, `language`, and the same card labels plus `unlisted`, `unlistedExplanation`, `unknownHall`, and `serviceCharge`. Implement it exactly as a `<section aria-labelledby=...>` with an `h2`; use `hall.hall_title || labels.unknownHall` for listed halls and `labels.unlisted` for the synthetic group. Render the explanation only for `!hall.is_listed`, render the hall service percentage only when it is non-null, and map `hall.tables.slice().sort(naturalTableSort)` through `TableInspectionCard` inside `.staff-tables__grid`.

- [ ] **Step 4: Implement the page, role routes, menu mode, and localized navigation**

In `StaffTablesPage.tsx`, import `useCallback`, `useEffect`, `useMemo`, `useRef`, `useState`, `useTranslation`, `useNavigate`, `useSearchParams`, the three presentation components, `MenuCatalog`, `StaffLayout`, `getStaffTables`, `useVisiblePolling`, `useMenuStore`, `useAuthStore`, `formatDateTime`, and `../../staff-tables.css`. Use this exact state and derivation code:

```tsx
type WorkspaceView = 'tables' | 'menu';
type TableFilter = 'all' | 'active' | 'attention';

const httpStatus = (cause: unknown) =>
  (cause as { response?: { status?: number } } | null)?.response?.status;

const [searchParams, setSearchParams] = useSearchParams();
const navigate = useNavigate();
const { t, i18n } = useTranslation();
const view: WorkspaceView = searchParams.get('view') === 'menu' ? 'menu' : 'tables';
const filter = ['active', 'attention'].includes(searchParams.get('filter') ?? '')
  ? (searchParams.get('filter') as TableFilter)
  : 'all';
const load = useCallback(
  () => getStaffTables().then((response) => response.data.data),
  [],
);
const { data, loading, error, refresh } = useVisiblePolling(
  load,
  15_000,
  'staff-tables',
);
const refreshMe = useAuthStore((state) => state.refreshMe);
const menu = useMenuStore((state) => state.menu);
const menuLoading = useMenuStore((state) => state.loading);
const menuError = useMenuStore((state) => state.error);
const fetchMenu = useMenuStore((state) => state.fetchMenu);
const retryMenu = useMenuStore((state) => state.retry);

const setParam = (key: 'view' | 'filter', value: string) => {
  const params = new URLSearchParams(searchParams);
  params.set(key, value);
  setSearchParams(params);
};
const setView = (next: WorkspaceView) => setParam('view', next);
const setFilter = (next: TableFilter) => setParam('filter', next);

const filteredHalls = useMemo(() => (data?.halls ?? [])
  .map((hall) => ({
    ...hall,
    tables: hall.tables.filter((table) => {
      const hasAnyOrder = table.synchronized_order_count
        + table.processing_order_count
        + table.attention_order_count > 0;
      if (filter === 'active') return hasAnyOrder;
      if (filter === 'attention') return table.attention_order_count > 0;
      return true;
    }),
  }))
  .filter((hall) => hall.tables.length > 0), [data?.halls, filter]);
const directoryTableCount = useMemo(
  () => (data?.halls ?? []).reduce((sum, hall) => sum + hall.tables.length, 0),
  [data?.halls],
);
const hasCachedError = error !== null && data !== null;

useEffect(() => {
  if (view === 'menu') void fetchMenu();
}, [fetchMenu, view]);

useEffect(() => {
  if (httpStatus(error) !== 403) return;
  let cancelled = false;
  void refreshMe().finally(() => {
    if (!cancelled) navigate('/', { replace: true });
  });
  return () => { cancelled = true; };
}, [error, navigate, refreshMe]);

useEffect(() => {
  if (error === null) return;
  console.error('staff_tables_workspace_load_failed', {
    status: httpStatus(error) ?? 'network',
  });
}, [error]);

const hasFreshnessIssue = Boolean(
  hasCachedError
  || data?.freshness.directory_stale
  || data?.freshness.order_status_stale,
);
const previousIssue = useRef(false);
const [announcement, setAnnouncement] = useState('');
useEffect(() => {
  if (hasFreshnessIssue) {
    setAnnouncement(t(
      'staff_tables.refresh_failed',
      'Could not refresh. Showing cached data.',
    ));
  } else if (previousIssue.current) {
    setAnnouncement(t(
      'staff_tables.freshness_restored',
      'Data is up to date again.',
    ));
  }
  previousIssue.current = hasFreshnessIssue;
}, [hasFreshnessIssue, t]);
```

Render the following branch inside `<StaffLayout><main className="staff-tables">…</main></StaffLayout>`:

```tsx
<h1>{t('staff_tables.title', 'Tables')}</h1>
<TableWorkspaceToggle
  view={view}
  onChange={setView}
  labels={{
    group: t('staff_tables.workspace', 'Table workspace'),
    tables: t('staff_tables.tables', 'Tables'),
    menu: t('staff_tables.menu', 'Menu'),
  }}
/>
<div className="sr-only" aria-live="polite" aria-atomic="true">
  {announcement}
</div>

{view === 'tables' ? (
  <>
    <div className="staff-tables__refresh-row">
      {data && <span>{t('staff_tables.updated', 'Updated')} {formatDateTime(data.freshness.generated_at, i18n.language)}</span>}
      <button type="button" onClick={() => void refresh()}>
        {t('staff_tables.refresh', 'Refresh')}
      </button>
    </div>
    {data?.freshness.directory_stale && (
      <p className="staff-tables__warning">
        {t('staff_tables.directory_stale', 'Table list may be outdated. Last updated:')}{' '}
        {formatDateTime(data.freshness.directory_last_success_at, i18n.language)}
      </p>
    )}
    {(data?.freshness.order_status_stale || hasCachedError) && (
      <p className="staff-tables__warning">
        {hasCachedError && <span>{t('staff_tables.refresh_failed', 'Could not refresh. Showing cached data.')}</span>}
        <span>{t('staff_tables.status_stale', 'Order status may be outdated.')}</span>
        {data?.freshness.order_status_oldest_success_at && (
          <span>{t('staff_tables.last_confirmed', 'Last confirmed:')}{' '}
            {formatDateTime(data.freshness.order_status_oldest_success_at, i18n.language)}
          </span>
        )}
      </p>
    )}
    {loading && !data ? (
      <div className="staff-tables__skeletons" aria-busy="true" aria-label={t('common.loading', 'Loading...')} />
    ) : error !== null && !data && httpStatus(error) !== 403 ? (
      <section className="staff-tables__blocking-error">
        <p>{t('staff_tables.unavailable', 'Tables are temporarily unavailable.')}</p>
        <button type="button" onClick={() => void refresh()}>{t('staff_tables.retry', 'Retry')}</button>
      </section>
    ) : data && directoryTableCount === 0 ? (
      <section className="staff-tables__empty">
        <p>{t('staff_tables.empty_directory', 'AliPOS returned no tables.')}</p>
        <button type="button" onClick={() => void refresh()}>{t('staff_tables.retry', 'Retry')}</button>
      </section>
    ) : data ? (
      <>
        <div role="group" aria-label={t('staff_tables.filters', 'Table filters')} className="staff-tables__filters">
          {(['all', 'active', 'attention'] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {value === 'all'
                ? t('staff_tables.all', 'All')
                : value === 'active'
                  ? t('staff_tables.with_orders', 'With orders')
                  : t('staff_tables.attention', 'Attention')}
            </button>
          ))}
        </div>
        {filteredHalls.length === 0 ? (
          <p>{t('staff_tables.no_filter_results', 'No tables match this filter.')}</p>
        ) : filteredHalls.map((hall) => (
          <TableHallSection
            key={hall.hall_id ?? 'unlisted'}
            hall={hall}
            language={i18n.language}
            labels={buildTableLabels(t)}
          />
        ))}
      </>
    ) : null}
  </>
) : (
  <>
    <div role="note" className="staff-tables__browse-note">
      {t('staff_tables.browse_only', 'Browse only · Orders cannot be placed here')}
    </div>
    {menu ? (
      <MenuCatalog
        menu={menu}
        language={i18n.language}
        mode="browse"
        labels={{
          soldOut: t('menu.sold_out', 'Sold out'),
          add: t('menu.add', 'Add'),
          remove: t('menu.remove', 'Remove'),
          limit: t('menu.limit', 'Available quantity is already in the cart'),
          empty: t('menu.empty', 'No menu items'),
        }}
      />
    ) : menuError ? (
      <button type="button" onClick={() => void retryMenu()}>{t('staff_tables.retry', 'Retry')}</button>
    ) : (
      <div aria-busy={menuLoading}>{t('common.loading', 'Loading...')}</div>
    )}
  </>
)}
```

Implement `buildTableLabels(t)` immediately above the component with this exact shape:

```tsx
const buildTableLabels = (t: TFunction) => ({
  details: (title: string) => `${t('staff_tables.view_details', 'View table details:')} ${title}`,
  unknownTable: t('staff_tables.unknown_table', 'Unnamed table'),
  unknownHall: t('staff_tables.unknown_hall', 'Unnamed hall'),
  unknownItem: t('staff_tables.unknown_item', 'Item'),
  noOrders: t('staff_tables.no_orders', 'No mini-app orders'),
  miniAppOrders: (count: number) => t('staff_tables.mini_app_orders', {
    count,
    defaultValue: '{{count}} mini-app orders',
  }),
  moreItems: (count: number) => t('staff_tables.more_items', {
    count,
    defaultValue: '+{{count}} more',
  }),
  processing: (count: number) => t('staff_tables.processing_count', {
    count,
    defaultValue: '{{count}} processing',
  }),
  attention: (count: number) => t('staff_tables.attention_count', {
    count,
    defaultValue: '{{count}} need attention',
  }),
  unlisted: t('staff_tables.unlisted', 'Unlisted tables'),
  unlistedExplanation: t(
    'staff_tables.unlisted_explanation',
    'These tables are no longer in the current AliPOS list; saved order details are shown.',
  ),
  serviceCharge: (percent: number) => t('staff_tables.service_charge', {
    percent,
    defaultValue: '{{percent}}% service',
  }),
});
```

Import `TFunction` from `i18next`. `With orders` is defined as synchronized + processing + attention greater than zero. All query changes preserve the other key and push browser history, so direct loads and Back/Forward work. Never read `useCartStore` in this page.

Add to `App.tsx`:

```tsx
import StaffTablesPage from './pages/staff/StaffTablesPage';

<Route path="/staff/tables" element={renderStaffOrAdminRoute(<StaffTablesPage />)} />
```

Update `StaffLayout` active states and nav arrays:

```tsx
const { t } = useTranslation();
const tablesActive = location.pathname.startsWith('/staff/tables');

const sharedItems = [
  { active: tablesActive, icon: 'table_restaurant', label: t('staff_tables.nav_tables', 'Tables'), to: '/staff/tables' },
  { active: ordersActive, icon: 'receipt_long', label: t('staff_tables.nav_delivery', 'Delivery'), to: '/staff/orders' },
  { active: profileActive, icon: 'person', label: t('nav.profile', 'Profile'), to: '/profile' },
];
const navItems = isAdmin
  ? [{ active: adminActive, icon: 'admin_panel_settings', label: t('staff_tables.nav_admin', 'Admin'), to: '/admin' }, ...sharedItems]
  : sharedItems;
```

Import `useTranslation` from `react-i18next`. Keep `getNavStyle(navItems.length)` so staff renders exactly three equal columns and admin exactly four; `tablesActive` must remain true on both overview and detail routes.

Add these exact top-level locale objects. They intentionally include the detail-page keys used in Task 9 so Task 9 only needs to consume, not invent, copy:

```json
// en.json
"staff_tables": {
  "nav_admin": "Admin", "nav_tables": "Tables", "nav_delivery": "Delivery",
  "title": "Tables", "workspace": "Table workspace", "tables": "Tables", "menu": "Menu",
  "browse_only": "Browse only · Orders cannot be placed here",
  "all": "All", "with_orders": "With orders", "attention": "Attention", "filters": "Table filters",
  "updated": "Updated", "refresh": "Refresh", "retry": "Retry",
  "directory_stale": "Table list may be outdated. Last updated:",
  "status_stale": "Order status may be outdated.", "last_confirmed": "Last confirmed:",
  "refresh_failed": "Could not refresh. Showing cached data.",
  "freshness_restored": "Data is up to date again.",
  "unavailable": "Tables are temporarily unavailable.",
  "empty_directory": "AliPOS returned no tables.",
  "no_filter_results": "No tables match this filter.",
  "no_orders": "No mini-app orders",
  "mini_app_orders": "{{count}} mini-app orders", "mini_app_orders_one": "{{count}} mini-app order", "mini_app_orders_other": "{{count}} mini-app orders",
  "processing_count": "{{count}} processing", "attention_count": "{{count}} need attention",
  "unlisted": "Unlisted tables",
  "unlisted_explanation": "These tables are no longer in the current AliPOS list; saved order details are shown.",
  "service_charge": "{{percent}}% service", "more_items": "+{{count}} more",
  "view_details": "View table details:", "unknown_table": "Unnamed table", "unknown_hall": "Unnamed hall", "unknown_item": "Item",
  "back_to_tables": "Back to tables", "combined_summary": "Combined summary", "combined_items": "Combined items", "original_orders": "Original orders",
  "synchronized_orders": "Synchronized", "processing_orders": "Processing", "attention_orders": "Needs attention",
  "items_cost": "Items", "service_amount": "Service", "total_amount": "Total",
  "synchronized": "Synchronized", "processing": "Processing", "verify_pos": "Verify in POS", "not_synchronized": "Not synchronized", "active": "Active",
  "not_found": "Table not found", "order": "Order", "modifiers": "Modifiers",
  "payment_cash": "Cash", "payment_online": "Online", "payment_paid": "Paid", "payment_unknown": "Payment status unknown"
}

// ru.json
"staff_tables": {
  "nav_admin": "Админ", "nav_tables": "Столы", "nav_delivery": "Доставка",
  "title": "Столы", "workspace": "Рабочая область столов", "tables": "Столы", "menu": "Меню",
  "browse_only": "Только просмотр · Здесь нельзя оформить заказ",
  "all": "Все", "with_orders": "С заказами", "attention": "Требуют внимания", "filters": "Фильтры столов",
  "updated": "Обновлено", "refresh": "Обновить", "retry": "Повторить",
  "directory_stale": "Список столов может быть устаревшим. Последнее обновление:",
  "status_stale": "Статусы заказов могут быть устаревшими.", "last_confirmed": "Последняя проверка:",
  "refresh_failed": "Не удалось обновить данные. Показана сохранённая версия.",
  "freshness_restored": "Данные снова актуальны.",
  "unavailable": "Столы временно недоступны.",
  "empty_directory": "AliPOS не вернул ни одного стола.",
  "no_filter_results": "Нет столов, подходящих под этот фильтр.",
  "no_orders": "Нет заказов из мини-приложения",
  "mini_app_orders": "Заказов из мини-приложения: {{count}}", "mini_app_orders_one": "{{count}} заказ из мини-приложения", "mini_app_orders_few": "{{count}} заказа из мини-приложения", "mini_app_orders_many": "{{count}} заказов из мини-приложения", "mini_app_orders_other": "{{count}} заказа из мини-приложения",
  "processing_count": "В обработке: {{count}}", "attention_count": "Требуют внимания: {{count}}",
  "unlisted": "Столы вне текущего списка",
  "unlisted_explanation": "Этих столов больше нет в текущем списке AliPOS; показаны сохранённые данные заказа.",
  "service_charge": "Обслуживание {{percent}}%", "more_items": "Ещё {{count}}",
  "view_details": "Открыть данные стола:", "unknown_table": "Стол без названия", "unknown_hall": "Зал без названия", "unknown_item": "Позиция",
  "back_to_tables": "К столам", "combined_summary": "Общая сводка", "combined_items": "Общие позиции", "original_orders": "Исходные заказы",
  "synchronized_orders": "Синхронизированы", "processing_orders": "В обработке", "attention_orders": "Требуют внимания",
  "items_cost": "Позиции", "service_amount": "Обслуживание", "total_amount": "Итого",
  "synchronized": "Синхронизирован", "processing": "В обработке", "verify_pos": "Проверьте в POS", "not_synchronized": "Не синхронизирован", "active": "Активен",
  "not_found": "Стол не найден", "order": "Заказ", "modifiers": "Добавки",
  "payment_cash": "Наличные", "payment_online": "Онлайн", "payment_paid": "Оплачено", "payment_unknown": "Статус оплаты неизвестен"
}

// uz.json
"staff_tables": {
  "nav_admin": "Admin", "nav_tables": "Stollar", "nav_delivery": "Yetkazib berish",
  "title": "Stollar", "workspace": "Stollar ish oynasi", "tables": "Stollar", "menu": "Menyu",
  "browse_only": "Faqat ko‘rish · Bu yerdan buyurtma berib bo‘lmaydi",
  "all": "Barchasi", "with_orders": "Buyurtmali", "attention": "E’tibor kerak", "filters": "Stol filtrlari",
  "updated": "Yangilandi", "refresh": "Yangilash", "retry": "Qayta urinish",
  "directory_stale": "Stollar ro‘yxati eskirgan bo‘lishi mumkin. So‘nggi yangilanish:",
  "status_stale": "Buyurtma holatlari eskirgan bo‘lishi mumkin.", "last_confirmed": "So‘nggi tekshiruv:",
  "refresh_failed": "Ma’lumotni yangilab bo‘lmadi. Saqlangan ma’lumot ko‘rsatilmoqda.",
  "freshness_restored": "Ma’lumot yana dolzarb.",
  "unavailable": "Stollar hozircha mavjud emas.",
  "empty_directory": "AliPOS hech qanday stol qaytarmadi.",
  "no_filter_results": "Bu filtrga mos stol yo‘q.",
  "no_orders": "Mini-ilova buyurtmalari yo‘q",
  "mini_app_orders": "{{count}} ta mini-ilova buyurtmasi", "mini_app_orders_one": "{{count}} ta mini-ilova buyurtmasi", "mini_app_orders_other": "{{count}} ta mini-ilova buyurtmasi",
  "processing_count": "Jarayonda: {{count}}", "attention_count": "E’tibor kerak: {{count}}",
  "unlisted": "Joriy ro‘yxatda yo‘q stollar",
  "unlisted_explanation": "Bu stollar AliPOS joriy ro‘yxatida yo‘q; buyurtmaning saqlangan ma’lumoti ko‘rsatilgan.",
  "service_charge": "Xizmat {{percent}}%", "more_items": "Yana {{count}} ta",
  "view_details": "Stol ma’lumotini ochish:", "unknown_table": "Nomsiz stol", "unknown_hall": "Nomsiz zal", "unknown_item": "Mahsulot",
  "back_to_tables": "Stollarga qaytish", "combined_summary": "Umumiy xulosa", "combined_items": "Umumiy mahsulotlar", "original_orders": "Asl buyurtmalar",
  "synchronized_orders": "Sinxronlangan", "processing_orders": "Jarayonda", "attention_orders": "E’tibor kerak",
  "items_cost": "Mahsulotlar", "service_amount": "Xizmat", "total_amount": "Jami",
  "synchronized": "Sinxronlangan", "processing": "Jarayonda", "verify_pos": "POS tizimida tekshiring", "not_synchronized": "Sinxronlanmagan", "active": "Faol",
  "not_found": "Stol topilmadi", "order": "Buyurtma", "modifiers": "Qo‘shimchalar",
  "payment_cash": "Naqd", "payment_online": "Onlayn", "payment_paid": "To‘langan", "payment_unknown": "To‘lov holati noma’lum"
}
```

The comments label destination files and are not copied into JSON. Preserve valid commas around the inserted object.

Create `frontend/src/i18n/staffTablesLocales.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import en from './locales/en.json';
import ru from './locales/ru.json';
import uz from './locales/uz.json';

const required = [
  'nav_admin', 'nav_tables', 'nav_delivery', 'title', 'workspace', 'tables', 'menu',
  'browse_only', 'all', 'with_orders', 'attention', 'updated', 'refresh', 'retry',
  'directory_stale', 'status_stale', 'last_confirmed', 'refresh_failed', 'freshness_restored',
  'unavailable', 'empty_directory', 'no_filter_results', 'no_orders',
  'mini_app_orders_one', 'mini_app_orders_other', 'processing_count', 'attention_count',
  'unlisted', 'unlisted_explanation', 'service_charge', 'more_items', 'view_details',
  'unknown_table', 'unknown_hall', 'unknown_item', 'back_to_tables',
  'combined_summary', 'combined_items', 'original_orders', 'synchronized_orders',
  'processing_orders', 'attention_orders', 'items_cost', 'service_amount',
  'total_amount', 'synchronized', 'processing', 'verify_pos', 'not_synchronized',
  'active', 'not_found', 'order', 'modifiers', 'payment_cash', 'payment_online',
  'payment_paid', 'payment_unknown',
] as const;

describe.each([['en', en], ['ru', ru], ['uz', uz]])('%s staff table copy', (_name, locale) => {
  it('defines every required non-empty string', () => {
    for (const key of required) {
      expect(locale.staff_tables[key], key).toEqual(expect.any(String));
      expect(locale.staff_tables[key].trim(), key).not.toBe('');
    }
  });
});
```

Create `frontend/src/staff-tables.css` with the concrete responsive/accessibility baseline below; Task 9 may append detail selectors but must preserve these rules:

```css
.staff-tables {
  min-width: 0;
  padding: 0 16px calc(24px + env(safe-area-inset-bottom));
}

.staff-tables h1,
.staff-tables h2,
.staff-tables h3,
.staff-table-card,
.staff-table-card * {
  min-width: 0;
  overflow-wrap: anywhere;
}

.staff-tables__toggle,
.staff-tables__filters,
.staff-tables__refresh-row,
.staff-table-card__states {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.staff-tables button,
.staff-tables a,
.staff-tables__toggle button,
.staff-tables__filters button {
  min-width: 44px;
  min-height: 44px;
}

.staff-tables :is(button, a):focus-visible {
  outline: 3px solid #a33800;
  outline-offset: 3px;
}

.staff-tables__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(136px, 1fr));
  gap: 12px;
}

.staff-table-card {
  display: flex;
  min-height: 152px;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid rgba(45, 47, 47, 0.16);
  border-radius: 14px;
  background: #fff;
  color: #2d2f2f;
  text-decoration: none;
}

.staff-table-card--active {
  border-color: #a33800;
  box-shadow: inset 4px 0 #a33800;
}

.staff-table-card__neutral {
  color: #656666;
}

.staff-tables__warning,
.staff-tables__browse-note {
  margin: 12px 0;
  padding: 12px;
  border-radius: 12px;
  background: #fff3ed;
  color: #6f2700;
  line-height: 1.5;
}

.staff-tables__warning > span { display: block; }

.staff-tables__skeletons {
  min-height: 280px;
  border-radius: 14px;
  background: linear-gradient(90deg, #eee 25%, #f8f8f8 50%, #eee 75%);
  background-size: 200% 100%;
  animation: staff-tables-shimmer 1.2s linear infinite;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes staff-tables-shimmer {
  to { background-position: -200% 0; }
}

@media (max-width: 340px) {
  .staff-tables { padding-inline: 12px; }
  .staff-tables__grid { gap: 8px; }
}

@media (max-width: 307px) {
  .staff-tables__grid { grid-template-columns: minmax(0, 1fr); }
}

@media (min-width: 341px) and (max-width: 389px) {
  .staff-tables { padding-inline: 16px; }
}

@media (min-width: 390px) and (max-width: 430px) {
  .staff-tables { padding-inline: 18px; }
}

@media (prefers-reduced-motion: reduce) {
  .staff-tables__skeletons { animation: none; }
}
```

At 320, 375, and 430 pixels the available content width keeps two cards at or above 136 pixels; below that capacity the grid naturally falls to one column. Auto heights, wrapped text, and `min-width: 0` preserve large-text layouts.

- [ ] **Step 5: Run focused UI tests and commit**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx src/components/artisan/ArtisanLayout.test.tsx src/components/staff/StaffLayout.test.tsx src/components/menu/MenuCatalog.test.tsx src/pages/staff/StaffTablesPage.test.tsx src/hooks/useVisiblePolling.test.tsx src/i18n/staffTablesLocales.test.ts && npm run typecheck
cd .. && ! rg -n "useCartStore|useTableOrderStore|checkout|createOrder" frontend/src/pages/staff/StaffTablesPage.tsx frontend/src/components/menu/MenuCatalog.tsx
```

Expected: PASS.

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/artisan/ArtisanLayout.test.tsx frontend/src/components/staff/StaffLayout.tsx frontend/src/components/staff/StaffLayout.test.tsx frontend/src/components/staff/TableWorkspaceToggle.tsx frontend/src/components/staff/TableInspectionCard.tsx frontend/src/components/staff/TableHallSection.tsx frontend/src/pages/staff/StaffTablesPage.tsx frontend/src/pages/staff/StaffTablesPage.test.tsx frontend/src/staff-tables.css frontend/src/i18n/staffTablesLocales.test.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
git commit -m "feat: add staff tables workspace"
```

---

### Task 9: Add the combined table detail page

**Files:**
- Create: `frontend/src/pages/staff/StaffTableDetailPage.tsx`
- Create: `frontend/src/pages/staff/StaffTableDetailPage.test.tsx`
- Create: `frontend/src/components/staff/TableOrderSummary.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/staff-tables.css`

**Interfaces:**
- Exposes `/staff/tables/:tableId` to staff/admin.
- Polls `getStaffTable(tableId)` through `useVisiblePolling(..., tableId)` so direct route-parameter changes reload immediately.
- Renders synchronized combined summary first and original orders second.

- [ ] **Step 1: Write failing detail and route tests**

Create `StaffTableDetailPage.test.tsx` with this setup and executable state coverage:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StaffTableDetailPage from './StaffTableDetailPage';
import type { StaffTableDetail, StaffTableOrder } from '../../types/staffTables';

const apiMocks = vi.hoisted(() => ({ getStaffTable: vi.fn() }));
const authState = vi.hoisted(() => ({
  user: { role: 'staff' },
  refreshMe: vi.fn().mockResolvedValue({ role: 'staff' }),
}));
vi.mock('../../services/staffTablesApi', () => apiMocks);
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, options?: string | { defaultValue?: string; count?: number; percent?: number }) => {
        const value = typeof options === 'string' ? options : options?.defaultValue ?? _key;
        return value
          .replace('{{count}}', String(typeof options === 'object' ? options.count ?? '' : ''))
          .replace('{{percent}}', String(typeof options === 'object' ? options.percent ?? '' : ''));
      },
      i18n: { language: 'en' },
    }),
  };
});

const tableId = '11111111-1111-4111-8111-111111111111';
const freshness = {
  generated_at: '2026-07-15T09:00:00Z',
  directory_stale: false,
  directory_last_success_at: '2026-07-15T09:00:00Z',
  order_status_stale: false,
  order_status_oldest_success_at: '2026-07-15T09:00:00Z',
};
const order = (overrides: Partial<StaffTableOrder> = {}): StaffTableOrder => ({
  id: crypto.randomUUID(),
  order_number: '1042',
  created_at: '2026-07-15T08:45:00Z',
  status: 'NEW',
  sync_state: 'synchronized' as const,
  sync_label: 'synchronized' as const,
  payment_method: 'cash',
  payment_status: null,
  items: [{
    id: 'somsa', name: 'Classic Somsa', quantity: 1, price: 18000,
    modifications: [{ id: 'spicy', name: 'Spicy', quantity: 1, price: 1000 }],
  }],
  items_cost: 18000,
  service_amount: 1800,
  total_amount: 19800,
  ...overrides,
});
const detailFixture: StaffTableDetail = {
  freshness,
  table: {
    table_id: tableId,
    table_title: 'Table 2',
    hall_id: '22222222-2222-4222-8222-222222222222',
    hall_title: 'Main hall',
    service_percent: 10,
    is_listed: true,
    synchronized_order_count: 1,
    processing_order_count: 1,
    attention_order_count: 2,
    combined_item_count: 1,
    combined_line_count: 1,
    combined_items: [{
      id: 'somsa', name: 'Classic Somsa', quantity: 1, price: 18000,
      modifications: [{ id: 'spicy', name: 'Spicy', quantity: 1, price: 1000 }],
      line_total: 19000,
    }],
    items_cost: 18000,
    service_amount: 1800,
    total_amount: 19800,
  },
  orders: [
    order({}),
    order({ id: crypto.randomUUID(), order_number: null, sync_state: 'processing', sync_label: 'processing', total_amount: 22000 }),
    order({ id: crypto.randomUUID(), order_number: null, sync_state: 'attention', sync_label: 'not_synchronized', total_amount: 33000 }),
    order({ id: crypto.randomUUID(), order_number: null, sync_state: 'attention', sync_label: 'verify_in_pos', total_amount: 44000 }),
  ],
};

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={[`/staff/tables/${tableId}`]}>
      <Routes>
        <Route path="/staff/tables/:tableId" element={<StaffTableDetailPage />} />
        <Route path="/staff/tables" element={<div>Tables destination</div>} />
        <Route path="/" element={<div>Role home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDetail(fixture: StaffTableDetail = detailFixture) {
  apiMocks.getStaffTable.mockResolvedValue({ data: { success: true, data: fixture } });
  return renderRoute();
}

describe('StaffTableDetailPage', () => {
  afterEach(() => vi.restoreAllMocks());

  beforeEach(() => vi.clearAllMocks());

  it('shows combined content first, safe sync labels, groups, and modifiers', async () => {
    const { container } = renderDetail();
    expect(await screen.findByText('Combined items')).toBeInTheDocument();
    expect(screen.getByText('Original orders')).toBeInTheDocument();
    expect(container.textContent?.indexOf('Combined items')).toBeLessThan(
      container.textContent?.indexOf('Original orders') ?? 0,
    );
    expect(screen.getByRole('heading', { name: 'Synchronized' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Processing' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument();
    expect(screen.getByText('Not synchronized')).toBeInTheDocument();
    expect(screen.getByText('Verify in POS')).toBeInTheDocument();
    expect(screen.getAllByText(/Spicy/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('19,800 UZS')).toHaveLength(2);
    expect(screen.getByText('22,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('33,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('44,000 UZS')).toBeInTheDocument();
    expect(screen.queryByText(/phone|telegram|11111111/i)).not.toBeInTheDocument();
  });

  it('renders loading, blocking retry, and a dedicated 404 state', async () => {
    const user = userEvent.setup();
    let resolve!: (value: unknown) => void;
    apiMocks.getStaffTable.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const loading = renderRoute();
    expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
    loading.unmount();
    resolve({ data: { success: true, data: detailFixture } });

    apiMocks.getStaffTable
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { success: true, data: detailFixture } });
    const retry = renderRoute();
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Combined items')).toBeInTheDocument();
    retry.unmount();

    apiMocks.getStaffTable.mockRejectedValue({ response: { status: 404 } });
    renderRoute();
    expect(await screen.findByText('Table not found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('keeps cached detail after refresh failure and preserves saved unlisted metadata', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const unlisted = {
      ...detailFixture,
      table: {
        ...detailFixture.table,
        is_listed: false,
        table_title: 'Patio 9',
        hall_title: 'Old patio',
        service_percent: 12,
      },
    };
    apiMocks.getStaffTable
      .mockResolvedValueOnce({ data: { success: true, data: unlisted } })
      .mockRejectedValueOnce({ response: { status: 503 } });
    renderRoute();
    expect(await screen.findByText('Old patio')).toBeInTheDocument();
    expect(screen.getByText('12% service')).toBeInTheDocument();
    expect(screen.getByText('Unlisted tables')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect((await screen.findAllByText('Could not refresh. Showing cached data.')).length).toBeGreaterThan(0);
    expect(consoleError).toHaveBeenCalledWith(
      'staff_tables_workspace_load_failed',
      { status: 503 },
    );
    expect(screen.getByText('Patio 9')).toBeInTheDocument();
  });

  it('uses localized Order instead of exposing an internal id and returns to overview', async () => {
    const user = userEvent.setup();
    renderDetail();
    expect((await screen.findAllByText('Order')).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('link', { name: 'Back to tables' }));
    expect(screen.getByText('Tables destination')).toBeInTheDocument();
  });

  it('rehydrates role and redirects after authoritative 403', async () => {
    apiMocks.getStaffTable.mockRejectedValue({ response: { status: 403 } });
    renderRoute();
    expect(await screen.findByText('Role home')).toBeInTheDocument();
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);
  });
});
```

Add to `App.test.tsx`:

```tsx
vi.mock('./pages/staff/StaffTableDetailPage', () => ({
  default: () => <div>Staff table detail page</div>,
}));

it('lets staff and admin open table detail but redirects customers', () => {
  for (const role of ['staff', 'admin']) {
    cleanup();
    authState.user = { role };
    render(
      <MemoryRouter initialEntries={['/staff/tables/11111111-1111-4111-8111-111111111111']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText('Staff table detail page')).toBeInTheDocument();
  }

  cleanup();
  authState.user = { role: 'customer' };
  render(
    <MemoryRouter initialEntries={['/staff/tables/11111111-1111-4111-8111-111111111111']}>
      <App />
    </MemoryRouter>,
  );
  expect(screen.getByText('Artisan menu page')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
cd frontend && npm test -- src/pages/staff/StaffTableDetailPage.test.tsx src/App.test.tsx
```

Expected: FAIL because page, component, and route do not exist.

- [ ] **Step 3: Implement order summary presentation**

Create `TableOrderSummary.tsx` with no API calls. Import `useTranslation`, `Icon`, `StaffTableOrder`, `formatDateTime`, and `formatPrice`, then implement the complete safe presentation below:

```tsx
export default function TableOrderSummary({ order }: { order: StaffTableOrder }) {
  const { t, i18n } = useTranslation();
  const knownStatuses: Record<string, string> = {
    PAID_AWAITING_RESTAURANT: t('status.placed', 'Placed'),
    NEW: t('status.placed', 'Placed'),
    ACCEPTED_BY_RESTAURANT: t('status.preparing', 'Preparing'),
    READY: t('status.ready', 'Ready'),
  };
  const statusCopy = order.sync_label === 'verify_in_pos'
    ? t('staff_tables.verify_pos', 'Verify in POS')
    : order.sync_label === 'not_synchronized'
      ? t('staff_tables.not_synchronized', 'Not synchronized')
      : order.sync_label === 'processing'
        ? t('staff_tables.processing', 'Processing')
        : knownStatuses[order.status] ?? t('staff_tables.active', 'Active');
  const paymentCopy = order.payment_method === 'cash'
    ? t('staff_tables.payment_cash', 'Cash')
    : order.payment_status === 'paid'
      ? `${t('staff_tables.payment_online', 'Online')} · ${t('staff_tables.payment_paid', 'Paid')}`
      : `${t('staff_tables.payment_online', 'Online')} · ${t('staff_tables.payment_unknown', 'Payment status unknown')}`;
  const stateIcon = order.sync_label === 'processing'
    ? 'hourglass_top'
    : order.sync_label === 'verify_in_pos' || order.sync_label === 'not_synchronized'
      ? 'warning'
      : 'check_circle';

  return (
    <article className={`staff-table-order staff-table-order--${order.sync_state}`}>
      <header>
        <strong>{order.order_number ? `#${order.order_number}` : t('staff_tables.order', 'Order')}</strong>
        <span><span aria-hidden="true"><Icon name={stateIcon} /></span>{statusCopy}</span>
      </header>
      <p>
        <time dateTime={order.created_at}>{formatDateTime(order.created_at, i18n.language)}</time>
        {' · '}{paymentCopy}
      </p>
      <ul className="staff-table-order__items">
        {order.items.map((item, index) => {
          const lineTotal = item.price * item.quantity + item.modifications.reduce(
            (sum, modifier) => sum + modifier.price * modifier.quantity,
            0,
          );
          return (
            <li key={`${item.id}-${item.price}-${index}`}>
              <span>{item.name || t('staff_tables.unknown_item', 'Item')} × {item.quantity}</span>
              {item.modifications.length > 0 && (
                <ul aria-label={t('staff_tables.modifiers', 'Modifiers')}>
                  {item.modifications.map((modifier, modifierIndex) => (
                    <li key={`${modifier.id}-${modifier.price}-${modifierIndex}`}>
                      {modifier.name || t('staff_tables.modifiers', 'Modifiers')} × {modifier.quantity}
                    </li>
                  ))}
                </ul>
              )}
              <span>{formatPrice(lineTotal, i18n.language)}</span>
            </li>
          );
        })}
      </ul>
      <dl className="staff-table-order__totals">
        <div><dt>{t('staff_tables.items_cost', 'Items')}</dt><dd>{formatPrice(order.items_cost, i18n.language)}</dd></div>
        <div><dt>{t('staff_tables.service_amount', 'Service')}</dt><dd>{formatPrice(order.service_amount, i18n.language)}</dd></div>
        <div><dt>{t('staff_tables.total_amount', 'Total')}</dt><dd>{formatPrice(order.total_amount, i18n.language)}</dd></div>
      </dl>
    </article>
  );
}
```

Only the order number is displayed; `order.id` is reserved for the parent React key. Unknown provider statuses map to localized `Active`, never raw provider copy. Text and an icon accompany every sync distinction, so color is supplementary.

- [ ] **Step 4: Implement the detail route page**

In `StaffTableDetailPage.tsx`, import React state/effect helpers, `Link`, `useNavigate`, `useParams`, `useTranslation`, `StaffLayout`, `TableOrderSummary`, `getStaffTable`, `useVisiblePolling`, `useAuthStore`, `formatDateTime`, `formatPrice`, and `../../staff-tables.css`. Use the same `httpStatus` helper as the overview and this route loader:

```tsx
const { tableId } = useParams();
const navigate = useNavigate();
const { t, i18n } = useTranslation();
const load = useCallback(async () => {
  if (!tableId) throw new Error(t('staff_tables.not_found', 'Table not found'));
  const response = await getStaffTable(tableId);
  return response.data.data;
}, [tableId, t]);
const { data, loading, error, refresh } = useVisiblePolling(
  load,
  15_000,
  tableId,
);
const refreshMe = useAuthStore((state) => state.refreshMe);

useEffect(() => {
  if (httpStatus(error) !== 403) return;
  let cancelled = false;
  void refreshMe().finally(() => {
    if (!cancelled) navigate('/', { replace: true });
  });
  return () => { cancelled = true; };
}, [error, navigate, refreshMe]);

useEffect(() => {
  if (error === null) return;
  console.error('staff_tables_workspace_load_failed', {
    status: httpStatus(error) ?? 'network',
  });
}, [error]);

const groupedOrders = data ? [
  {
    key: 'synchronized',
    title: t('staff_tables.synchronized_orders', 'Synchronized'),
    orders: data.orders.filter((order) => order.sync_state === 'synchronized'),
  },
  {
    key: 'processing',
    title: t('staff_tables.processing_orders', 'Processing'),
    orders: data.orders.filter((order) => order.sync_state === 'processing'),
  },
  {
    key: 'attention',
    title: t('staff_tables.attention_orders', 'Needs attention'),
    orders: data.orders.filter((order) => order.sync_state === 'attention'),
  },
].filter((group) => group.orders.length > 0) : [];

const hasCachedError = error !== null && data !== null;
const hasFreshnessIssue = Boolean(
  hasCachedError
  || data?.freshness.directory_stale
  || data?.freshness.order_status_stale,
);
const previousIssue = useRef(false);
const [announcement, setAnnouncement] = useState('');
useEffect(() => {
  if (hasFreshnessIssue) {
    setAnnouncement(t('staff_tables.refresh_failed', 'Could not refresh. Showing cached data.'));
  } else if (previousIssue.current) {
    setAnnouncement(t('staff_tables.freshness_restored', 'Data is up to date again.'));
  }
  previousIssue.current = hasFreshnessIssue;
}, [hasFreshnessIssue, t]);
```

Render inside `<StaffLayout><main className="staff-tables staff-table-detail">…</main></StaffLayout>` using this branch. Reuse the overview's issue-transition live-region effect so cached failure and recovery are announced once, not on successful polls:

```tsx
<div className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</div>
<Link to="/staff/tables" className="staff-table-detail__back">
  {t('staff_tables.back_to_tables', 'Back to tables')}
</Link>

{loading && !data ? (
  <div className="staff-tables__skeletons" aria-busy="true" aria-label={t('common.loading', 'Loading...')} />
) : httpStatus(error) === 404 && !data ? (
  <p>{t('staff_tables.not_found', 'Table not found')}</p>
) : error !== null && !data && httpStatus(error) !== 403 ? (
  <section className="staff-tables__blocking-error">
    <p>{t('staff_tables.unavailable', 'Tables are temporarily unavailable.')}</p>
    <button type="button" onClick={() => void refresh()}>{t('staff_tables.retry', 'Retry')}</button>
  </section>
) : data ? (
  <>
    <header className="staff-table-detail__header">
      <div>
        <h1>{data.table.table_title || t('staff_tables.unknown_table', 'Unnamed table')}</h1>
        <p>{data.table.hall_title || t('staff_tables.unknown_hall', 'Unnamed hall')}</p>
        <p>{t('staff_tables.service_charge', {
          percent: data.table.service_percent,
          defaultValue: '{{percent}}% service',
        })}</p>
      </div>
      {!data.table.is_listed && (
        <div>
          <strong>{t('staff_tables.unlisted', 'Unlisted tables')}</strong>
          <p>{t(
            'staff_tables.unlisted_explanation',
            'These tables are no longer in the current AliPOS list; saved order details are shown.',
          )}</p>
        </div>
      )}
      <button type="button" onClick={() => void refresh()}>{t('staff_tables.refresh', 'Refresh')}</button>
    </header>

    {data.freshness.directory_stale && (
      <p className="staff-tables__warning">
        {t('staff_tables.directory_stale', 'Table list may be outdated. Last updated:')}{' '}
        {formatDateTime(data.freshness.directory_last_success_at, i18n.language)}
      </p>
    )}
    {(data.freshness.order_status_stale || hasCachedError) && (
      <p className="staff-tables__warning">
        {hasCachedError && <span>{t('staff_tables.refresh_failed', 'Could not refresh. Showing cached data.')}</span>}
        <span>{t('staff_tables.status_stale', 'Order status may be outdated.')}</span>
        {data.freshness.order_status_oldest_success_at && (
          <span>{t('staff_tables.last_confirmed', 'Last confirmed:')}{' '}
            {formatDateTime(data.freshness.order_status_oldest_success_at, i18n.language)}
          </span>
        )}
      </p>
    )}

    <section className="staff-table-detail__combined">
      <h2>{t('staff_tables.combined_summary', 'Combined summary')}</h2>
      <p>{t('staff_tables.mini_app_orders', {
        count: data.table.synchronized_order_count,
        defaultValue: '{{count}} mini-app orders',
      })}</p>
      <p>{data.table.combined_item_count} {t('staff_tables.combined_items', 'Combined items')}</p>
      <dl>
        <div><dt>{t('staff_tables.items_cost', 'Items')}</dt><dd>{formatPrice(data.table.items_cost, i18n.language)}</dd></div>
        <div><dt>{t('staff_tables.service_amount', 'Service')}</dt><dd>{formatPrice(data.table.service_amount, i18n.language)}</dd></div>
        <div><dt>{t('staff_tables.total_amount', 'Total')}</dt><dd>{formatPrice(data.table.total_amount, i18n.language)}</dd></div>
      </dl>
      <h2>{t('staff_tables.combined_items', 'Combined items')}</h2>
      <ul>
        {data.table.combined_items.map((item, index) => (
          <li key={`${item.id}-${item.price}-${index}`}>
            <span>{item.name || t('staff_tables.unknown_item', 'Item')} × {item.quantity}</span>
            {item.modifications.length > 0 && (
              <ul aria-label={t('staff_tables.modifiers', 'Modifiers')}>
                {item.modifications.map((modifier, modifierIndex) => (
                  <li key={`${modifier.id}-${modifier.price}-${modifierIndex}`}>
                    {modifier.name || t('staff_tables.modifiers', 'Modifiers')} × {modifier.quantity}
                  </li>
                ))}
              </ul>
            )}
            <span>{formatPrice(item.line_total, i18n.language)}</span>
          </li>
        ))}
      </ul>
    </section>

    <section className="staff-table-detail__orders">
      <h2>{t('staff_tables.original_orders', 'Original orders')}</h2>
      {groupedOrders.map((group) => (
        <section key={group.key}>
          <h3>{group.title}</h3>
          {group.orders.map((order) => (
            <TableOrderSummary key={order.id} order={order} />
          ))}
        </section>
      ))}
    </section>
  </>
) : null}
```

The combined card reads only backend aggregate fields. It never sums processing or attention orders in React. For an unlisted table, retain and render the persisted `hall_title` and `service_percent`; `Unlisted tables` is a separate badge/explanation, not a replacement header.

Add the route after `/staff/tables`:

```tsx
<Route
  path="/staff/tables/:tableId"
  element={renderStaffOrAdminRoute(<StaffTableDetailPage />)}
/>
```

All copy is already defined and parity-tested in Task 8; do not add raw status, payment, or identifier fallbacks here.

Append these detail styles to `staff-tables.css`:

```css
.staff-table-detail__back {
  display: inline-flex;
  align-items: center;
  margin-bottom: 16px;
  color: #7c2d12;
  font-weight: 800;
}

.staff-table-detail__header,
.staff-table-detail__combined,
.staff-table-order {
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid rgba(45, 47, 47, 0.14);
  border-radius: 14px;
  background: #fff;
}

.staff-table-detail__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.staff-table-detail dl,
.staff-table-order__totals {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
}

.staff-table-detail dl > div,
.staff-table-order__totals > div,
.staff-table-order > header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.staff-table-detail dd {
  margin: 0;
  font-weight: 800;
  text-align: end;
}

.staff-table-order--processing {
  border-inline-start: 4px solid #9a6700;
}

.staff-table-order--attention {
  border-inline-start: 4px solid #b31b25;
}

.staff-table-order__items,
.staff-table-order__items ul,
.staff-table-detail__combined ul {
  padding-inline-start: 20px;
}

@media (max-width: 340px) {
  .staff-table-detail__header,
  .staff-table-detail dl > div,
  .staff-table-order__totals > div,
  .staff-table-order > header {
    align-items: stretch;
    flex-direction: column;
  }

  .staff-table-detail dd { text-align: start; }
}
```

- [ ] **Step 5: Run frontend regression tests and commit**

Run:

```bash
cd frontend && npm test -- src/pages/staff/StaffTableDetailPage.test.tsx src/pages/staff/StaffTablesPage.test.tsx src/components/staff/StaffLayout.test.tsx src/App.test.tsx && npm run typecheck && npm run lint
```

Expected: PASS.

```bash
git add frontend/src/pages/staff/StaffTableDetailPage.tsx frontend/src/pages/staff/StaffTableDetailPage.test.tsx frontend/src/components/staff/TableOrderSummary.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/staff-tables.css
git commit -m "feat: add staff table order detail"
```

---

### Task 10: Add an executable rollout and rollback runbook

**Files:**
- Create: `docs/admin-staff-table-inspection-rollout.md`

**Interfaces:**
- Uses the safe backend `staff_table_status_reconcile claimed=… succeeded=… failed=… duration_ms=…` event added in Task 4.
- Uses the privacy-safe frontend `staff_tables_workspace_load_failed` console event added in Tasks 8 and 9.
- Defines a 15-minute controlled watch, measurable pass thresholds, and immediate rollback triggers for the deployed `restaurant` host.

- [ ] **Step 1: Write the rollout runbook with concrete signals and thresholds**

Create `docs/admin-staff-table-inspection-rollout.md`:

````markdown
# Admin and Staff Table Inspection Rollout

## Safety boundary

Deploy the additive migration first, then backend, then frontend. Use only controlled staff and admin accounts during the release watch. Do not log or copy customer data, local/provider order IDs, access tokens, or AliPOS payloads into rollout evidence.

The release has two feature-specific signals:

- Backend: `staff_table_status_reconcile claimed=<n> succeeded=<n> failed=<n> duration_ms=<n>`; this contains counts only.
- Frontend: `staff_tables_workspace_load_failed { status: <code|network> }`; this contains no URL, table ID, response body, token, or customer field.

Uvicorn access logs provide `/api/staff/tables` response status. This repository has no centralized browser telemetry, so the controlled frontend watch below uses the browser Console and Network panels explicitly; do not claim an unconfigured dashboard exists.

## Before deployment

1. Record the current backend and frontend image IDs:

```bash
ssh restaurant 'wsl docker inspect --format="{{.Image}}" restaurant_backend restaurant_frontend'
```

2. Apply the idempotent migration and verify both columns and the partial index using the production commands approved for this host.
3. Record the number of eligible synchronized table orders at the beginning of the controlled watch:

```sql
SELECT count(*) AS eligible_orders
FROM orders
WHERE discriminator = 'inplace'
  AND table_id IS NOT NULL
  AND alipos_order_id IS NOT NULL
  AND alipos_sync_status = 'synced'
  AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED', 'AWAITING_PAYMENT', 'PAYMENT_FAILED', 'PAYMENT_REVIEW')
  AND (payment_method = 'cash' OR payment_status = 'paid');
```

Call this value `ELIGIBLE_ORDERS`. If table orders are created, completed, or cancelled during the watch, discard the rate calculation and restart a stable 15-minute window with a new count.

## Controlled 15-minute watch

1. Immediately before opening the candidate UI, record the UTC start time:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
```

2. Open one staff session and one admin session with browser DevTools open and `Preserve log` enabled in both Console and Network. During the next 15 minutes:
   - keep the Tables overview visible for at least two polling intervals;
   - open one table detail and keep it visible for at least two polling intervals;
   - switch to Menu and back;
   - perform four manual refreshes separated by at least five seconds;
   - verify every request is read-only and no cart/checkout/order-create request occurs.
3. At 15 minutes, capture backend logs from the same interval:

```bash
ssh restaurant 'wsl docker logs --since 15m restaurant_backend 2>&1' > /tmp/staff-tables-release.log
```

4. Count workspace requests and server failures:

```bash
rg -c 'GET /api/staff/tables' /tmp/staff-tables-release.log
rg 'GET /api/staff/tables' /tmp/staff-tables-release.log | rg ' 5[0-9]{2} '
rg 'GET /api/staff/tables' /tmp/staff-tables-release.log | rg ' 403 '
```

5. Sum claimed provider reads from the safe batch events:

```bash
awk '/staff_table_status_reconcile / {
  for (i = 1; i <= NF; i += 1) {
    if ($i ~ /^claimed=/) {
      split($i, pair, "=");
      claimed += pair[2];
    }
  }
}
END { print claimed + 0 }' /tmp/staff-tables-release.log
```

For a stable 15-minute window the upper bound is `ELIGIBLE_ORDERS × 31` claims (one possible claim at each 30-second boundary, including both endpoints). The automated cross-worker test is the authoritative per-order throttle proof; this production count is a runaway-rate guard.

## Pass criteria

All of the following must be true before the release owner accepts the candidate:

- At least eight controlled overview/detail requests appear in the access log.
- No controlled authorized request returns 403 or any 5xx. A deliberately induced no-cache AliPOS outage is tested outside this normal-provider watch and is not mixed into these counts.
- Total `claimed` is at most `ELIGIBLE_ORDERS × 31` for an unchanged eligible set.
- Every reconcile line contains counts/duration only; no UUID, token, provider body, phone, name, or address appears.
- Neither browser Console contains `staff_tables_workspace_load_failed` during the stable-provider watch.
- Neither Network panel contains a failed JS/CSS chunk or failed Tables/Menu/detail request.
- The UI smoke checks in the implementation plan pass for staff and admin, and customer ordering/delivery remain unchanged.

Retain `/tmp/staff-tables-release.log`, the start/end UTC timestamps, request/5xx/403 counts, claimed total, eligible-order count, and screenshots of the filtered Console/Network panels as the release evidence. Do not retain customer-bearing screenshots or response bodies.

## Immediate rollback triggers

Restore both recorded application images if any authorized route is blocked, any table/order response exposes a forbidden field, browse mode exposes a mutation control, the claim bound is exceeded, repeated 5xx responses occur with a healthy provider, a frontend failure marker appears during the stable watch, or customer ordering/delivery regresses. The nullable columns and partial index may remain; dropping them is a separately reviewed maintenance action.
````

- [ ] **Step 2: Verify the runbook and feature signals are present**

Run after Tasks 4, 8, and 9 are implemented:

```bash
rg -n "staff_table_status_reconcile|staff_tables_workspace_load_failed" backend/app/services/staff_table_service.py frontend/src/pages/staff/StaffTablesPage.tsx frontend/src/pages/staff/StaffTableDetailPage.tsx docs/admin-staff-table-inspection-rollout.md
pandoc -f gfm -t html docs/admin-staff-table-inspection-rollout.md -o /tmp/admin-staff-table-inspection-rollout.html
git diff --check
```

Expected: both privacy-safe signals appear in implementation and documentation, Pandoc parses the runbook, and no whitespace error is reported.

- [ ] **Step 3: Commit the rollout runbook**

```bash
git add docs/admin-staff-table-inspection-rollout.md
git commit -m "docs: add table inspection rollout runbook"
```

---

## Final verification gate

Run these commands from a clean working tree after Task 9:

```bash
cd backend && .venv/bin/python -m pytest -q
cd ../frontend && npm test
npm run typecheck
npm run lint
npm run build
cd ..
set -a
source .env
set +a
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < database/migrations/2026-07-15-staff-table-inspection.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < database/migrations/2026-07-15-staff-table-inspection.sql
git diff --check
! rg -n "useCartStore|useTableOrderStore|checkout|createOrder" frontend/src/pages/staff/StaffTablesPage.tsx frontend/src/components/menu/MenuCatalog.tsx
```

Expected:

- Complete backend suite passes with zero failures.
- Complete frontend suite passes with zero failures.
- TypeScript reports no errors.
- ESLint reports no errors.
- Vite production build exits successfully.
- The migration applies twice without error against the disposable/local Postgres database.
- `git diff --check` reports no whitespace errors.
- Browse-only modules contain no cart, table-context, checkout, or order-create dependency.

Perform these manual read-only checks against the exact candidate build:

1. Staff navigation shows `Tables | Delivery | Profile`.
2. Admin navigation shows `Admin | Tables | Delivery | Profile`.
3. Every live directory table appears, including tables with no mini-app order.
4. One table with multiple synchronized mini-app orders shows correct combined items/totals and separate original orders.
5. Processing and attention records never inflate combined synchronized totals.
6. A stale-directory or status-read failure keeps cached data visible with an explicit warning.
7. Browse-only menu matches the customer catalog but has no add/remove/cart/checkout controls.
8. Customer menu ordering and staff delivery flows still work unchanged.
9. Uzbek, Russian, and English layouts remain usable at 320, 375, and 430 pixels.

## Release and rollback sequence

Do not deploy until all automated commands and manual checks pass and the release owner explicitly authorizes deployment. Then use this order:

1. Record the current backend and frontend image revisions for rollback.
2. Apply `database/migrations/2026-07-15-staff-table-inspection.sql` to production before either application image. Confirm both nullable columns and `idx_orders_inplace_workspace` exist; no backfill is expected.
3. Deploy the backend image. Smoke-check that a customer receives 403, staff/admin receive 200, an empty directory is distinct from a 503, and an existing synchronized table order returns only the privacy-minimized contract.
4. Deploy the frontend image. Smoke-check staff/admin navigation, one neutral table, one synchronized aggregate/detail, processing/attention exclusion, browse-only menu, and all three languages.
5. Execute the controlled 15-minute watch in `docs/admin-staff-table-inspection-rollout.md`. Accept only if it records at least eight controlled requests, zero authorized 403/5xx responses, zero frontend failure markers, no failed candidate assets/API calls, and total claimed status reads no greater than `ELIGIBLE_ORDERS × 31` for an unchanged eligible set. Any threshold breach is an immediate rollback trigger.

If rollback is required, restore the recorded frontend and backend image revisions together. The two nullable timestamp columns and partial index are additive and may remain safely; remove them only in a separately reviewed maintenance migration. Rollback must not change customer table-payment gates, order totals, refunds, cancellation, or the delivery staff workflow.
