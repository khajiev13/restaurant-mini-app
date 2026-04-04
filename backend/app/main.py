import asyncio
import datetime
import logging

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.routers import addresses, auth, geocoding, menu, orders, users, webhooks

logger = logging.getLogger(__name__)
PAYMENTS_EXPIRY_LOCK_ID = 841_337_204

app = FastAPI(title="Mr.Pub Restaurant API", version="0.1.0")


@app.on_event("startup")
async def register_telegram_webhook() -> None:
    if not settings.public_base_url or not settings.telegram_bot_token:
        return

    webhook_url = f"{settings.public_base_url}/api/webhooks/bot"
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram webhook auto-registration failed: %s", exc)


@app.on_event("startup")
async def start_payment_expiry_task() -> None:
    """Start the background task that expires unpaid Rahmat orders after their TTL."""
    asyncio.create_task(_expire_pending_payments())


async def _expire_pending_payments() -> None:
    """Background task: expire unpaid Rahmat orders past their payment deadline.

    Runs every `payment_expiry_check_interval_seconds`. For each expired-but-pending
    order, marks it expired then attempts a best-effort AliPOS cancellation.
    """
    from sqlalchemy import select, text

    from app.database import async_session
    from app.models.models import Order
    from app.services import alipos_api, multicard_api

    while True:
        await asyncio.sleep(settings.payment_expiry_check_interval_seconds)

        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

        # Collect IDs and alipos IDs to process outside the session
        expired_records: list[tuple[str, str | None, str | None]] = []  # (order_id, alipos_order_id, mc_invoice_uuid)

        try:
            async with async_session() as db:
                lock_result = await db.execute(
                    text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                    {"lock_id": PAYMENTS_EXPIRY_LOCK_ID},
                )
                if not bool(lock_result.scalar()):
                    await db.rollback()
                    continue

                result = await db.execute(
                    select(Order).where(
                        Order.payment_status == "pending",
                        Order.payment_expires_at.is_not(None),
                        Order.payment_expires_at <= now,
                    )
                )
                expired = result.scalars().all()

                if not expired:
                    continue

                for order in expired:
                    order.payment_status = "expired"
                    order.status = "CANCELLED"
                    order.payment_error = "Payment timeout — invoice expired after 10 minutes"
                    expired_records.append((
                        str(order.id),
                        str(order.alipos_order_id) if order.alipos_order_id else None,
                        order.multicard_invoice_uuid,
                    ))

                await db.commit()

            logger.info("Expired %d unpaid Rahmat orders", len(expired_records))
        except Exception as exc:
            logger.exception("Error during payment expiry check: %s", exc)
            continue

        # Best-effort: cancel Multicard invoices and AliPOS orders
        for order_id, alipos_order_id, mc_invoice_uuid in expired_records:
            if mc_invoice_uuid:
                await multicard_api.cancel_invoice(mc_invoice_uuid)

            if alipos_order_id:
                try:
                    await alipos_api.cancel_order(alipos_order_id)
                    cancel_status = "cancelled"
                    cancel_error = None
                    logger.info("AliPOS cancel succeeded for order %s", order_id)
                except Exception as exc:
                    cancel_status = "failed"
                    cancel_error = str(exc)[:500]
                    logger.warning("AliPOS cancel failed for order %s: %s", order_id, exc)

                try:
                    async with async_session() as db:
                        import uuid as _uuid

                        from sqlalchemy import select as sel

                        from app.models.models import Order as O
                        result = await db.execute(sel(O).where(O.id == _uuid.UUID(order_id)))
                        o = result.scalar_one_or_none()
                        if o:
                            o.alipos_cancel_status = cancel_status
                            if cancel_error:
                                o.alipos_cancel_error = cancel_error
                            await db.commit()
                except Exception as exc:
                    logger.exception("Failed to save AliPOS cancel status for order %s: %s", order_id, exc)


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
app.include_router(addresses.router, prefix="/api")
app.include_router(geocoding.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")


@app.get("/health", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}
