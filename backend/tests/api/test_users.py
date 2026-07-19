from app.config import settings
from app.middleware.telegram_auth import create_jwt
from app.models.models import User
from app.services.phone_verification_service import phone_verification_fingerprint


async def _user(db_session, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        first_name="Tester",
        last_name=None,
        username=None,
    )
    db_session.add(user)
    await db_session.commit()
    return user


def _configure_rollout(monkeypatch, *, enabled: bool, test_ids: str) -> None:
    monkeypatch.setitem(settings.__dict__, "inplace_online_payment_enabled", enabled)
    monkeypatch.setitem(
        settings.__dict__,
        "inplace_online_payment_test_telegram_ids",
        test_ids,
    )


def _assert_capability_only(data: dict, *, enabled: bool) -> None:
    assert data["inplace_online_payment_enabled"] is enabled
    assert "inplace_online_payment_test_telegram_ids" not in data
    assert "inplace_online_payment_test_ids" not in data


async def test_get_me_exposes_allowlisted_inplace_online_payment_capability(
    client,
    db_session,
    monkeypatch,
):
    user = await _user(db_session, 7301)
    _configure_rollout(monkeypatch, enabled=False, test_ids="7301,7302")

    response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
    )

    assert response.status_code == 200
    _assert_capability_only(response.json()["data"], enabled=True)


async def test_update_me_exposes_global_inplace_online_payment_capability(
    client,
    db_session,
    monkeypatch,
):
    user = await _user(db_session, 7303)
    _configure_rollout(monkeypatch, enabled=True, test_ids="")

    response = await client.put(
        "/api/users/me",
        headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
        json={"language": "ru"},
    )

    assert response.status_code == 200
    _assert_capability_only(response.json()["data"], enabled=True)
    assert response.json()["data"]["language"] == "ru"
    await db_session.refresh(user)
    assert user.language == "ru"


async def test_get_me_exposes_verified_phone_without_verification_metadata(client, db_session):
    user = await _user(db_session, 7304)
    user.phone_number = "+998901234567"
    user.phone_verified_at = user.created_at
    user.phone_verified_message_at = user.created_at
    user.phone_verified_update_id = 7304
    user.phone_verified_fingerprint = phone_verification_fingerprint(
        user.telegram_id,
        user.phone_number,
    )
    await db_session.commit()

    response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["phone_verified"] is True
    assert {
        "phone_verified_at",
        "phone_verified_fingerprint",
        "phone_verified_message_at",
        "phone_verified_update_id",
    }.isdisjoint(data)


async def test_update_me_rejects_phone_number_and_preserves_the_existing_value(client, db_session):
    user = await _user(db_session, 7305)
    user.phone_number = "+998901234567"
    await db_session.commit()

    response = await client.put(
        "/api/users/me",
        headers={"Authorization": f"Bearer {create_jwt(user.telegram_id)}"},
        json={"phone_number": "+998901112233"},
    )

    await db_session.refresh(user)
    assert response.status_code == 422
    assert user.phone_number == "+998901234567"
