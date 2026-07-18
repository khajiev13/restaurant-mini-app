import asyncio
import datetime
import logging
from contextlib import suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.routers import (
    addresses,
    admin,
    auth,
    geocoding,
    menu,
    orders,
    staff,
    tables,
    users,
    webhooks,
)
from app.services.telegram_webhook_service import register_telegram_webhook

logger = logging.getLogger(__name__)
PAYMENTS_EXPIRY_LOCK_ID = 841_337_204
PROVIDER_RECONCILIATION_MIN_INTERVAL_SECONDS = 1
PROVIDER_RECONCILIATION_MAX_INTERVAL_SECONDS = 3600

app = FastAPI(title="Mr.Pub Restaurant API", version="0.1.0")
app.router.add_event_handler("startup", register_telegram_webhook)


@app.on_event("startup")
async def start_payment_expiry_task() -> None:
    """Start the background task that expires unpaid Rahmat orders after their TTL."""
    asyncio.create_task(_expire_pending_payments())


@app.on_event("startup")
async def recover_paid_alipos_queue() -> None:
    from app.services.order_service import (
        recover_invoice_operations,
        recover_queued_alipos_orders,
        recover_refund_operations,
    )

    await recover_queued_alipos_orders()
    await recover_refund_operations()
    await recover_invoice_operations()


def _provider_reconciliation_interval_seconds() -> float:
    return min(
        max(
            float(settings.provider_reconciliation_interval_seconds),
            PROVIDER_RECONCILIATION_MIN_INTERVAL_SECONDS,
        ),
        PROVIDER_RECONCILIATION_MAX_INTERVAL_SECONDS,
    )


async def _reconcile_provider_operations_periodically() -> None:
    from app.services.order_service import reconcile_provider_operations

    while True:
        try:
            await reconcile_provider_operations()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error(
                "provider_reconciliation_tick_failed",
                extra={"reconciliation_outcome": "tick_error"},
            )
        await asyncio.sleep(_provider_reconciliation_interval_seconds())


@app.on_event("startup")
async def start_provider_reconciliation_task() -> None:
    current = getattr(app.state, "provider_reconciliation_task", None)
    if current is not None and not current.done():
        return
    app.state.provider_reconciliation_task = asyncio.create_task(
        _reconcile_provider_operations_periodically(),
        name="provider-reconciliation",
    )


@app.on_event("shutdown")
async def stop_provider_reconciliation_task() -> None:
    task = getattr(app.state, "provider_reconciliation_task", None)
    app.state.provider_reconciliation_task = None
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _expire_pending_payments() -> None:
    """Expire only unpaid invoices whose cancellation Multicard confirms."""
    from sqlalchemy import text

    from app.database import async_session
    from app.services.order_service import expire_due_payment_orders

    while True:
        await asyncio.sleep(settings.payment_expiry_check_interval_seconds)

        try:
            async with async_session() as db:
                lock_result = await db.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                    {"lock_id": PAYMENTS_EXPIRY_LOCK_ID},
                )
                if not bool(lock_result.scalar()):
                    await db.rollback()
                    continue
                expired_count = await expire_due_payment_orders(
                    db,
                    datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
                )
            if expired_count:
                logger.info("Expired %d unpaid Rahmat orders", expired_count)
        except Exception as exc:
            logger.exception("Error during payment expiry check: %s", exc)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_allowed_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.resolved_trusted_hosts,
)

app.include_router(auth.router, prefix="/api")
app.include_router(menu.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(addresses.router, prefix="/api")
app.include_router(geocoding.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(tables.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")


@app.get("/health", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
