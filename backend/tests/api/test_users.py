from app.config import settings
from app.middleware.telegram_auth import create_jwt
from app.models.models import User


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
