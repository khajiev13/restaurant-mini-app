from app.config import settings
from app.models.models import User
from app.services import order_service


def test_inplace_online_payment_test_ids_ignore_invalid_values(monkeypatch):
    monkeypatch.setitem(
        settings.__dict__,
        "inplace_online_payment_test_telegram_ids",
        "7301, invalid, 7302",
    )

    assert hasattr(settings, "inplace_online_payment_test_ids")
    assert settings.inplace_online_payment_test_ids == {7301, 7302}


def test_inplace_online_payment_capability_uses_global_flag_or_allowlist(monkeypatch):
    monkeypatch.setitem(settings.__dict__, "inplace_online_payment_enabled", False)
    monkeypatch.setitem(
        settings.__dict__,
        "inplace_online_payment_test_telegram_ids",
        "7301, invalid, 7302",
    )
    allowlisted = User(telegram_id=7301, first_name="Tester")
    customer = User(telegram_id=9999, first_name="Customer")

    assert hasattr(order_service, "can_use_inplace_online_payment")
    assert order_service.can_use_inplace_online_payment(allowlisted)
    assert not order_service.can_use_inplace_online_payment(customer)
