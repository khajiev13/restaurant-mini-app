from fastapi import APIRouter

from app.middleware.telegram_auth import DbDep
from app.schemas.common import ApiResponse
from app.services.menu_catalog_service import get_customer_menu

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("")
async def get_menu(db: DbDep) -> ApiResponse:
    """Return the full restaurant menu from AliPOS."""
    menu = await get_customer_menu(db)
    return ApiResponse(success=True, data=menu)
