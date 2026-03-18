from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.services import alipos_api

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("")
async def get_menu() -> ApiResponse:
    """Return the full restaurant menu from AliPOS."""
    menu = await alipos_api.get_menu()
    return ApiResponse(success=True, data=menu)
