import pytest

from app.middleware.telegram_auth import create_jwt
from app.models.models import User


def _auth_headers(telegram_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(telegram_id)}"}


async def _create_user(
    db_session,
    telegram_id: int,
    role: str,
    phone_number: str | None = None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name=f"User{telegram_id}",
        last_name=None,
        username=f"user{telegram_id}",
        phone_number=phone_number,
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_non_admin_cannot_search_users(client, db_session):
    staff = await _create_user(db_session, 801, "staff")

    response = await client.get(
        "/api/admin/users?query=user",
        headers=_auth_headers(staff.telegram_id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_search_users_by_phone(client, db_session):
    admin = await _create_user(db_session, 802, "admin")
    target = await _create_user(
        db_session,
        803,
        "customer",
        phone_number="+998901112233",
    )

    response = await client.get(
        "/api/admin/users?query=1112233",
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["telegram_id"] == target.telegram_id
    assert "inplace_online_payment_enabled" not in data[0]


@pytest.mark.asyncio
async def test_admin_can_assign_staff_role(client, db_session):
    admin = await _create_user(db_session, 804, "admin")
    target = await _create_user(db_session, 805, "customer")

    response = await client.patch(
        f"/api/admin/users/{target.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(admin.telegram_id),
    )

    await db_session.refresh(target)
    assert response.status_code == 200
    assert target.role == "staff"
    assert response.json()["data"]["role"] == "staff"
    assert "inplace_online_payment_enabled" not in response.json()["data"]


@pytest.mark.asyncio
async def test_non_admin_cannot_patch_user_role(client, db_session):
    staff = await _create_user(db_session, 809, "staff")
    target = await _create_user(db_session, 810, "customer")

    response = await client.patch(
        f"/api/admin/users/{target.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(staff.telegram_id),
    )

    await db_session.refresh(target)
    assert response.status_code == 403
    assert target.role == "customer"


@pytest.mark.asyncio
async def test_admin_role_patch_normalizes_role(client, db_session):
    admin = await _create_user(db_session, 811, "admin")
    target = await _create_user(db_session, 812, "customer")

    response = await client.patch(
        f"/api/admin/users/{target.telegram_id}/role",
        json={"role": " STAFF "},
        headers=_auth_headers(admin.telegram_id),
    )

    await db_session.refresh(target)
    assert response.status_code == 200
    assert target.role == "staff"
    assert response.json()["data"]["role"] == "staff"


@pytest.mark.asyncio
async def test_admin_cannot_assign_invalid_role(client, db_session):
    admin = await _create_user(db_session, 806, "admin")
    target = await _create_user(db_session, 807, "customer")

    response = await client.patch(
        f"/api/admin/users/{target.telegram_id}/role",
        json={"role": "superadmin"},
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_role_patch_returns_404_for_missing_user(client, db_session):
    admin = await _create_user(db_session, 813, "admin")

    response = await client.patch(
        "/api/admin/users/999999/role",
        json={"role": "staff"},
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_final_admin_cannot_remove_own_admin_role(client, db_session):
    admin = await _create_user(db_session, 808, "admin")

    response = await client.patch(
        f"/api/admin/users/{admin.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(admin.telegram_id),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot remove the final admin role."


@pytest.mark.asyncio
async def test_admin_can_demote_another_admin_when_one_admin_remains(client, db_session):
    acting_admin = await _create_user(db_session, 814, "admin")
    target_admin = await _create_user(db_session, 815, "admin")
    remaining_admin = await _create_user(db_session, 816, "admin")

    response = await client.patch(
        f"/api/admin/users/{target_admin.telegram_id}/role",
        json={"role": "staff"},
        headers=_auth_headers(acting_admin.telegram_id),
    )

    await db_session.refresh(target_admin)
    await db_session.refresh(remaining_admin)
    assert response.status_code == 200
    assert target_admin.role == "staff"
    assert remaining_admin.role == "admin"
    assert response.json()["data"]["role"] == "staff"
