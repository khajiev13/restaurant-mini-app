from fastapi import APIRouter, HTTPException, Query, status

from app.middleware.telegram_auth import CurrentUserDep
from app.schemas.common import ApiResponse
from app.services import yandex_geocoder

router = APIRouter(prefix="/geocode", tags=["geocoding"])


@router.get("/reverse")
async def reverse_geocode(
    current_user: CurrentUserDep,
    lat: float = Query(...),
    lng: float = Query(...),
    lang: str = Query("ru"),
) -> ApiResponse:
    try:
        data = await yandex_geocoder.reverse_geocode(lat=lat, lng=lng, lang=lang)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reverse geocode address: {exc}",
        ) from exc

    return ApiResponse(success=True, data=data)


@router.get("/suggest")
async def suggest_address(
    current_user: CurrentUserDep,
    text: str = Query(...),
    lang: str = Query("ru"),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
) -> ApiResponse:
    try:
        data = await yandex_geocoder.suggest(text=text, lang=lang, lat=lat, lng=lng)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch address suggestions: {exc}",
        ) from exc

    return ApiResponse(success=True, data=data)
