from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.user import SelfProfileResponse, UserUpdate
from app.services.order_service import can_use_inplace_online_payment

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(current_user: CurrentUserDep) -> ApiResponse:
    """Get current user's profile."""
    profile = SelfProfileResponse.model_validate(current_user)
    profile.inplace_online_payment_enabled = can_use_inplace_online_payment(current_user)
    return ApiResponse(
        success=True,
        data=profile.model_dump(),
    )


@router.put("/me")
async def update_me(
    body: UserUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Update current user's profile."""
    if body.language is not None:
        current_user.language = body.language
    await db.commit()
    await db.refresh(current_user)
    profile = SelfProfileResponse.model_validate(current_user)
    profile.inplace_online_payment_enabled = can_use_inplace_online_payment(current_user)
    return ApiResponse(
        success=True,
        data=profile.model_dump(),
    )
