import datetime
import re
import uuid
from decimal import Decimal

import pytest

from app.services.table_access_service import (
    InvalidTableEntry,
    TableAccessService,
    TableDirectoryEntry,
)

TABLE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
HALL_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _service() -> TableAccessService:
    return TableAccessService(
        secret="table-test-secret",
        bot_username="olotsomsa_zakaz_bot",
        access_ttl_seconds=8 * 60 * 60,
    )


def _entry() -> TableDirectoryEntry:
    return TableDirectoryEntry(
        table_id=TABLE_ID,
        table_title="Stol 12",
        hall_id=HALL_ID,
        hall_title="Asosiy zal",
        service_percent=Decimal("10"),
    )


def test_parse_table_directory_joins_a_validated_complete_directory():
    from app.services.table_access_service import parse_table_directory

    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Asosiy zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)},
        ],
    }

    assert parse_table_directory(payload) == [_entry()]


def test_table_codes_are_stable_six_character_crockford_values():
    service = _service()

    code = service.build_manual_code(TABLE_ID)

    assert code == service.build_manual_code(TABLE_ID)
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{6}", code)


def test_tampered_start_parameter_is_rejected():
    service = _service()
    start_param = service.build_start_param(TABLE_ID)

    replacement = "0" if start_param[-1] != "0" else "1"
    with pytest.raises(InvalidTableEntry, match="Invalid table QR"):
        service.parse_start_param(start_param[:-1] + replacement)


def test_access_token_round_trip_and_expiry():
    service = _service()
    issued_at = datetime.datetime(2026, 7, 13, 8, 0, tzinfo=datetime.UTC)
    token = service.issue_access_token(_entry(), now=issued_at)

    claims = service.verify_access_token(
        token, now=issued_at + datetime.timedelta(hours=1)
    )

    assert claims.table_id == TABLE_ID
    assert claims.expires_at == issued_at + datetime.timedelta(hours=8)

    with pytest.raises(InvalidTableEntry, match="expired"):
        service.verify_access_token(token, now=issued_at + datetime.timedelta(hours=9))


def test_resolve_code_returns_safe_table_context():
    service = _service()
    resolution = service.resolve_code(service.build_manual_code(TABLE_ID), [_entry()])

    assert resolution.table_title == "Stol 12"
    assert resolution.hall_title == "Asosiy zal"
    assert resolution.service_percent == Decimal("10")
    assert str(TABLE_ID) not in resolution.access_token
