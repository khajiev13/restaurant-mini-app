from __future__ import annotations

import asyncio
import datetime
import logging
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Order, User
from app.schemas.staff_table import (
    StaffHallResponse,
    StaffTableDetailResponse,
    StaffTableItemResponse,
    StaffTableModifierResponse,
    StaffTableOrderItemResponse,
    StaffTableOrderResponse,
    StaffTablesFreshnessResponse,
    StaffTablesOverviewResponse,
    StaffTableSummaryResponse,
    StaffTableSyncLabel,
    StaffTableSyncState,
)
from app.services import alipos_api
from app.services.order_status_service import (
    apply_alipos_status_update_for_order,
    normalize_order_status,
)
from app.services.permissions import require_staff
from app.services.table_access_service import TableDirectoryEntry, parse_table_directory

TERMINAL_TABLE_STATUSES = {"DELIVERED", "CANCELLED", "CANCELED"}
PRE_ORDER_STATUSES = {"AWAITING_PAYMENT", "PAYMENT_FAILED", "PAYMENT_REVIEW"}
PROCESSING_SYNC_STATES = {"queued", "sending"}
ATTENTION_SYNC_STATES = {"failed", "unknown"}
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
    return tuple(
        sorted(
            (
                str(modifier.get("id") or ""),
                _decimal(modifier.get("quantity")),
                _decimal(modifier.get("price")),
            )
            for modifier in modifications
        )
    )


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
    synchronized = [order for order, state in bucket.orders if state == "synchronized"]
    all_combined_items = aggregate_order_items(synchronized)
    visible_combined_items = (
        all_combined_items
        if combined_item_limit is None
        else all_combined_items[:combined_item_limit]
    )
    items_cost = sum(
        (_decimal(order.items_cost) for order in synchronized), Decimal("0")
    )
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
        processing_order_count=sum(state == "processing" for _, state in bucket.orders),
        attention_order_count=sum(state == "attention" for _, state in bucket.orders),
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
        order for order in orders if classify_table_order(order) == "synchronized"
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
    await db.commit()
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
            Order.alipos_sync_status.in_(
                ("synced", "queued", "sending", "failed", "unknown")
            ),
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
