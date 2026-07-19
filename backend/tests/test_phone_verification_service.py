import datetime
import re
from types import SimpleNamespace

import pytest

from app.services.phone_verification_service import (
    InvalidPhoneNumber,
    is_newer_contact_update,
    is_phone_verified,
    mask_phone_number,
    normalize_phone_number,
    phone_verification_fingerprint,
)


@pytest.mark.parametrize(
    ("raw_phone", "canonical_phone"),
    [
        ("+998 90 123-45-67", "+998901234567"),
        ("998 (90) 123 45 67", "+998901234567"),
        (" +44 (20) 1234-5678 ", "+442012345678"),
    ],
)
def test_normalize_phone_number_accepts_telegram_visual_formatting(raw_phone, canonical_phone):
    assert normalize_phone_number(raw_phone) == canonical_phone


@pytest.mark.parametrize(
    "raw_phone",
    [
        "998+901234567",
        "+998+901234567",
        "+99890abc4567",
        "+998.901234567",
        "+9989012",
        "+1234567890123456",
        None,
    ],
)
def test_normalize_phone_number_rejects_invalid_values(raw_phone):
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone_number(raw_phone)


def test_phone_verification_fingerprint_is_stable_and_bound_to_identity_and_phone():
    fingerprint = phone_verification_fingerprint(123, "+998901234567")

    assert fingerprint == phone_verification_fingerprint(123, "+998901234567")
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert fingerprint != phone_verification_fingerprint(124, "+998901234567")
    assert fingerprint != phone_verification_fingerprint(123, "+998901234568")


def _verified_user() -> SimpleNamespace:
    phone_number = "+998901234567"
    return SimpleNamespace(
        telegram_id=123,
        phone_number=phone_number,
        phone_verified_at=datetime.datetime(2026, 7, 19, tzinfo=datetime.UTC),
        phone_verified_message_at=datetime.datetime(2026, 7, 19, tzinfo=datetime.UTC),
        phone_verified_update_id=456,
        phone_verified_fingerprint=phone_verification_fingerprint(123, phone_number),
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "phone_number",
        "phone_verified_at",
        "phone_verified_message_at",
        "phone_verified_update_id",
        "phone_verified_fingerprint",
    ],
)
def test_is_phone_verified_requires_every_verification_field(field_name):
    user = _verified_user()
    setattr(user, field_name, None)

    assert is_phone_verified(user) is False


def test_is_phone_verified_rejects_a_fingerprint_for_a_different_phone():
    user = _verified_user()
    user.phone_verified_fingerprint = phone_verification_fingerprint(123, "+998901234568")

    assert is_phone_verified(user) is False


def test_is_phone_verified_accepts_a_complete_matching_state():
    assert is_phone_verified(_verified_user()) is True


def test_is_newer_contact_update_compares_message_time_before_update_id():
    user = _verified_user()
    message_at = user.phone_verified_message_at

    assert is_newer_contact_update(
        user,
        message_at + datetime.timedelta(seconds=1),
        update_id=1,
    ) is True
    assert is_newer_contact_update(user, message_at, update_id=457) is True
    assert is_newer_contact_update(user, message_at, update_id=456) is False
    assert is_newer_contact_update(
        user,
        message_at - datetime.timedelta(seconds=1),
        update_id=999,
    ) is False


def test_mask_phone_number_uses_the_exact_uzbek_display_format():
    assert mask_phone_number("+998901234567") == "+998 90 *** 4567"


def test_mask_phone_number_hides_at_least_three_digits_for_generic_numbers():
    masked_phone = mask_phone_number("+4412345678")

    assert masked_phone == "+441 *** 5678"
    assert masked_phone.count("*") >= 3
    assert masked_phone.endswith("5678")
