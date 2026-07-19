import datetime
import hashlib
import hmac


class InvalidPhoneNumber(ValueError):
    """Raised when a phone number is not valid Telegram contact input."""


_ALLOWED_PHONE_CHARACTERS = frozenset("+0123456789 -()")
_VISUAL_PHONE_SEPARATORS = " -()"


def normalize_phone_number(raw_phone: object) -> str:
    """Return a canonical ``+``-prefixed phone number from Telegram formatting."""
    if not isinstance(raw_phone, str) or not raw_phone:
        raise InvalidPhoneNumber("Phone number must be a non-empty string")
    if any(character not in _ALLOWED_PHONE_CHARACTERS for character in raw_phone):
        raise InvalidPhoneNumber("Phone number contains invalid characters")

    compact = raw_phone.translate(str.maketrans("", "", _VISUAL_PHONE_SEPARATORS))
    if compact.count("+") > 1 or ("+" in compact and not compact.startswith("+")):
        raise InvalidPhoneNumber("Phone number has a misplaced plus sign")

    digits = compact.removeprefix("+")
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise InvalidPhoneNumber("Phone number must contain 8 to 15 digits")
    return f"+{digits}"


def phone_verification_fingerprint(telegram_id: int, canonical_phone: str) -> str:
    """Bind a canonical verified phone to its Telegram identity."""
    payload = f"{telegram_id}:{canonical_phone}".encode()
    return hashlib.sha256(payload).hexdigest()


def is_phone_verified(user: object) -> bool:
    """Return whether a structural user object has complete matching verification data."""
    phone_number = getattr(user, "phone_number", None)
    fingerprint = getattr(user, "phone_verified_fingerprint", None)
    telegram_id = getattr(user, "telegram_id", None)
    required_metadata = (
        getattr(user, "phone_verified_at", None),
        getattr(user, "phone_verified_message_at", None),
        getattr(user, "phone_verified_update_id", None),
    )
    if (
        not isinstance(phone_number, str)
        or not isinstance(telegram_id, int)
        or isinstance(telegram_id, bool)
        or not isinstance(fingerprint, str)
        or any(value is None for value in required_metadata)
    ):
        return False

    try:
        canonical_phone = normalize_phone_number(phone_number)
    except InvalidPhoneNumber:
        return False
    if canonical_phone != phone_number:
        return False

    expected_fingerprint = phone_verification_fingerprint(telegram_id, canonical_phone)
    return len(fingerprint) == len(expected_fingerprint) and hmac.compare_digest(
        fingerprint,
        expected_fingerprint,
    )


def is_newer_contact_update(
    user: object,
    message_at: datetime.datetime,
    update_id: int,
) -> bool:
    """Return whether a Telegram contact pair sorts after the persisted pair."""
    previous_message_at = getattr(user, "phone_verified_message_at", None)
    previous_update_id = getattr(user, "phone_verified_update_id", None)
    if previous_message_at is None or previous_update_id is None:
        return True
    return (message_at, update_id) > (previous_message_at, previous_update_id)


def mask_phone_number(canonical_phone: str) -> str:
    """Return a compact phone reference that hides all but safe identifying digits."""
    canonical_phone = normalize_phone_number(canonical_phone)
    digits = canonical_phone[1:]
    if len(digits) == 12 and digits.startswith("998"):
        return f"+998 {digits[3:5]} *** {digits[-4:]}"

    prefix_length = min(3, len(digits) - 7)
    hidden_digits = len(digits) - prefix_length - 4
    return f"+{digits[:prefix_length]} {'*' * hidden_digits} {digits[-4:]}"
