import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.models.models import Address
from app.schemas.address import AddressCreate, AddressResponse
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("")
async def get_addresses(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    """Get all saved addresses for the current user."""
    result = await db.execute(
        select(Address).where(Address.user_id == current_user.telegram_id)
    )
    addresses = result.scalars().all()
    return ApiResponse(
        success=True,
        data=[AddressResponse.model_validate(a).model_dump() for a in addresses],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_address(
    body: AddressCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Add a new delivery address."""
    # If this is marked as default, unset other defaults
    if body.is_default:
        result = await db.execute(
            select(Address).where(
                Address.user_id == current_user.telegram_id,
                Address.is_default.is_(True),
            )
        )
        for addr in result.scalars().all():
            addr.is_default = False

    address = Address(
        user_id=current_user.telegram_id,
        label=body.label,
        full_address=body.full_address,
        latitude=body.latitude,
        longitude=body.longitude,
        is_default=body.is_default,
    )
    db.add(address)
    await db.commit()
    await db.refresh(address)
    return ApiResponse(
        success=True,
        data=AddressResponse.model_validate(address).model_dump(),
    )


@router.delete("/{address_id}")
async def delete_address(
    address_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Remove a saved address."""
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.telegram_id,
        )
    )
    address = result.scalar_one_or_none()
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )
    await db.delete(address)
    await db.commit()
    return ApiResponse(success=True)
