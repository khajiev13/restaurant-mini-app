import datetime
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.models.models import Order
from app.schemas.common import ApiResponse
from app.schemas.table import (
    TableContextResponse,
    TableManifestItem,
    TableResolveRequest,
)
from app.services.permissions import require_admin
from app.services.table_access_service import (
    InvalidTableDirectory,
    InvalidTableEntry,
    TableAccessService,
)

router = APIRouter(prefix="/tables", tags=["tables"])

table_access = TableAccessService(
    secret=settings.effective_table_access_secret,
    bot_username=settings.telegram_bot_username,
    access_ttl_seconds=settings.table_access_ttl_seconds,
)
TABLE_DIRECTORY_UNAVAILABLE = "Table directory is temporarily unavailable"


def _directory_unavailable(exc: InvalidTableDirectory) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=TABLE_DIRECTORY_UNAVAILABLE,
    )


def _context_response(resolved) -> dict:
    return TableContextResponse(
        table_title=resolved.table_title,
        hall_title=resolved.hall_title,
        service_percent=float(resolved.service_percent),
        manual_code=resolved.manual_code,
        access_token=resolved.access_token,
    ).model_dump()


@router.post("/resolve")
async def resolve_table(body: TableResolveRequest) -> ApiResponse:
    try:
        resolved = await table_access.resolve(body.entry, body.code)
    except InvalidTableDirectory as exc:
        raise _directory_unavailable(exc) from exc
    except InvalidTableEntry as exc:
        message = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if message == "Table code was not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=message) from exc
    return ApiResponse(
        success=True,
        data=_context_response(resolved),
    )


@router.post("/restore/{order_id}")
async def restore_table(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Restore table mode after Telegram opens a fresh payment-return WebView."""
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
            Order.discriminator == "inplace",
            Order.table_id.is_not(None),
            Order.table_access_expires_at.is_not(None),
            Order.table_access_expires_at
            > datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        )
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table order not found",
        )
    try:
        resolved = await table_access.restore(
            order.table_id,
            order.table_access_expires_at,
        )
    except InvalidTableDirectory as exc:
        raise _directory_unavailable(exc) from exc
    except InvalidTableEntry as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ApiResponse(success=True, data=_context_response(resolved))


@router.get("/manifest")
async def get_table_manifest(current_user: CurrentUserDep) -> ApiResponse:
    require_admin(current_user)
    try:
        manifest = await table_access.manifest()
    except InvalidTableDirectory as exc:
        raise _directory_unavailable(exc) from exc
    items = [
        TableManifestItem.model_validate(item).model_dump()
        for item in manifest
    ]
    return ApiResponse(success=True, data=items)
