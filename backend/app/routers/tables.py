from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.middleware.telegram_auth import CurrentUserDep
from app.schemas.common import ApiResponse
from app.schemas.table import (
    TableContextResponse,
    TableManifestItem,
    TableResolveRequest,
)
from app.services.permissions import require_admin
from app.services.table_access_service import InvalidTableEntry, TableAccessService

router = APIRouter(prefix="/tables", tags=["tables"])

table_access = TableAccessService(
    secret=settings.effective_table_access_secret,
    bot_username=settings.telegram_bot_username,
    access_ttl_seconds=settings.table_access_ttl_seconds,
)


@router.post("/resolve")
async def resolve_table(body: TableResolveRequest) -> ApiResponse:
    try:
        resolved = await table_access.resolve(body.entry, body.code)
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
        data=TableContextResponse(
            table_title=resolved.table_title,
            hall_title=resolved.hall_title,
            service_percent=float(resolved.service_percent),
            manual_code=resolved.manual_code,
            access_token=resolved.access_token,
        ).model_dump(),
    )


@router.get("/manifest")
async def get_table_manifest(current_user: CurrentUserDep) -> ApiResponse:
    require_admin(current_user)
    items = [
        TableManifestItem.model_validate(item).model_dump()
        for item in await table_access.manifest()
    ]
    return ApiResponse(success=True, data=items)
