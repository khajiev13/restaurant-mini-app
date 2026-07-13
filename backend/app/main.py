import asyncio
import datetime
import logging
from typing import Any

import httpx
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

logger = logging.getLogger(__name__)
PAYMENTS_EXPIRY_LOCK_ID = 841_337_204
TELEGRAM_ALLOWED_UPDATES = ["message"]

app = FastAPI(title="Mr.Pub Restaurant API", version="0.1.0")


async def _get_telegram_webhook_info(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo",
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"getWebhookInfo failed: {payload}")
    return payload["result"]


def _normalized_allowed_updates(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted(values)


@app.on_event("startup")
async def register_telegram_webhook() -> None:
    if not settings.public_base_url or not settings.telegram_bot_token:
        return

    webhook_url = f"{settings.public_base_url}/api/webhooks/bot"
    payload: dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": TELEGRAM_ALLOWED_UPDATES,
    }
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    async with httpx.AsyncClient() as client:
        try:
            try:
                current_info = await _get_telegram_webhook_info(client)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Telegram webhook inspection failed; will attempt setWebhook: %s",
                    exc,
                )
            else:
                current_url = current_info.get("url", "")
                current_allowed_updates = _normalized_allowed_updates(
                    current_info.get("allowed_updates")
                )
                expected_allowed_updates = _normalized_allowed_updates(
                    TELEGRAM_ALLOWED_UPDATES
                )
                if (
                    current_url == webhook_url
                    and current_allowed_updates == expected_allowed_updates
                ):
                    logger.info(
                        "Telegram webhook already configured for %s; skipping setWebhook",
                        webhook_url,
                    )
                    return

            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Telegram webhook registered for %s", webhook_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram webhook auto-registration failed: %s", exc)


@app.on_event("startup")
async def start_payment_expiry_task() -> None:
    """Start the background task that expires unpaid Rahmat orders after their TTL."""
    asyncio.create_task(_expire_pending_payments())


@app.on_event("startup")
async def recover_paid_alipos_queue() -> None:
    from app.services.order_service import (
        recover_queued_alipos_orders,
        recover_refund_operations,
    )

    await recover_queued_alipos_orders()
    await recover_refund_operations()


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
