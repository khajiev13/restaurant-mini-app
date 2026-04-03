from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.middleware.telegram_auth import DbDep, create_jwt, validate_init_data
from app.models.models import User
from app.schemas.common import ApiResponse
from app.schemas.user import TelegramAuthRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram")
async def telegram_auth(body: TelegramAuthRequest, db: DbDep) -> ApiResponse:
    """Validate Telegram initData, create/update user, return JWT."""
    try:
        user_data = validate_init_data(body.init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    telegram_id = user_data["id"]
    photo_url = user_data.get("photo_url")
    if not photo_url:
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                photos_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUserProfilePhotos"
                photos_resp = await client.get(photos_url, params={"user_id": telegram_id, "limit": 1}, timeout=5.0)
                if photos_resp.is_success and photos_resp.json().get("ok"):
                    result = photos_resp.json().get("result", {})
                    if result.get("total_count", 0) > 0 and result.get("photos"):
                        # Get the smallest photo size (index 0)
                        file_id = result["photos"][0][0]["file_id"]
                        file_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile"
                        file_resp = await client.get(file_url, params={"file_id": file_id}, timeout=5.0)
                        if file_resp.is_success and file_resp.json().get("ok"):
                            file_path = file_resp.json()["result"]["file_path"]
                            photo_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
        except Exception:
            pass

    # Upsert user
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        user.first_name = user_data.get("first_name", user.first_name)
        user.last_name = user_data.get("last_name")
        user.username = user_data.get("username")
        if photo_url:
            user.photo_url = photo_url
    else:
        user = User(
            telegram_id=telegram_id,
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            photo_url=photo_url,
        )
        db.add(user)

    await db.commit()

    token = create_jwt(telegram_id)
    return ApiResponse(
        success=True,
        data=TokenResponse(access_token=token).model_dump(),
    )
