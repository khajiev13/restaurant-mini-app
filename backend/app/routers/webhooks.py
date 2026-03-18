import datetime
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.models import Order, Stoplist

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_webhook_credentials(client_id: str | None, client_secret: str | None) -> None:
    """Verify that AliPOS webhook headers match our credentials."""
    import hmac as _hmac

    if not client_id or not client_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")

    id_ok = _hmac.compare_digest(client_id, settings.alipos_api_client_id)
    secret_ok = _hmac.compare_digest(client_secret, settings.alipos_api_client_secret)
    if not id_ok or not secret_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


@router.post("/order-status")
async def order_status_webhook(
    request: Request,
    clientid: str | None = Header(None, alias="clientId"),
    clientsecret: str | None = Header(None, alias="clientSecret"),
) -> dict:
    """Receive order status updates from AliPOS."""
    _verify_webhook_credentials(clientid, clientsecret)

    body = await request.json()
    eats_id = body.get("eatsId")
    new_status = body.get("status")
    order_number = body.get("orderNumber")

    if not eats_id or not new_status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing eatsId or status")

    async with async_session() as db:
        result = await db.execute(
            select(Order).where(Order.alipos_eats_id == eats_id)
        )
        order = result.scalar_one_or_none()
        if order:
            order.status = new_status
            order.order_number = order_number
            order.status_updated_at = datetime.datetime.now(datetime.UTC)
            await db.commit()

    return {"result": "OK"}


@router.post("/stoplist/{product_id}")
async def stoplist_webhook(
    product_id: uuid.UUID,
    restaurantId: str,
    count: int,
    clientid: str | None = Header(None, alias="clientId"),
    clientsecret: str | None = Header(None, alias="clientSecret"),
) -> dict:
    """Receive stop-list updates from AliPOS."""
    _verify_webhook_credentials(clientid, clientsecret)

    restaurant_uuid = uuid.UUID(restaurantId)

    async with async_session() as db:
        result = await db.execute(
            select(Stoplist).where(
                Stoplist.product_id == product_id,
                Stoplist.restaurant_id == restaurant_uuid,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.count = count
            entry.updated_at = datetime.datetime.now(datetime.UTC)
        else:
            db.add(
                Stoplist(
                    product_id=product_id,
                    restaurant_id=restaurant_uuid,
                    count=count,
                )
            )
        await db.commit()

    return {"result": "OK"}
