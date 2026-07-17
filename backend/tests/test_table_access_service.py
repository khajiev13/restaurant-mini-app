import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.table_access_service import (
    InvalidTableDirectory,
    InvalidTableEntry,
    TableAccessService,
    TableDirectoryEntry,
    get_table_directory,
    manual_code_from_title,
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
        manual_code="12",
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Stol 1", "1"),
        ("Table 12", "12"),
        ("Stol 007", "7"),
        ("VIP Stol 25", "25"),
        ("Stol 000", "0"),
    ],
)
def test_manual_code_uses_trailing_table_number(title, expected):
    assert manual_code_from_title(title) == expected


@pytest.mark.parametrize("title", ["Stol", "Stol 1234567", "Stol 12 VIP", ""])
def test_manual_code_rejects_titles_without_one_to_six_trailing_digits(title):
    with pytest.raises(InvalidTableDirectory):
        manual_code_from_title(title)


@pytest.mark.asyncio
async def test_directory_rejects_duplicate_numeric_codes_across_halls():
    other_hall_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    other_table_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Asosiy zal", "servicePercent": 10},
            {"id": str(other_hall_id), "title": "Terrace", "servicePercent": 15},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)},
            {
                "id": str(other_table_id),
                "title": "Table 012",
                "hallId": str(other_hall_id),
            },
        ],
    }

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(InvalidTableDirectory, match="Duplicate table number 12"):
            await get_table_directory()


@pytest.mark.parametrize("service_percent", ["invalid", "NaN", "Infinity"])
@pytest.mark.asyncio
async def test_directory_rejects_invalid_service_percent(service_percent):
    payload = {
        "halls": [
            {
                "id": str(HALL_ID),
                "title": "Asosiy zal",
                "servicePercent": service_percent,
            }
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)}
        ],
    }

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(
            InvalidTableDirectory, match="Hall directory entry is invalid"
        ):
            await get_table_directory()


def test_numeric_start_parameter_round_trips_with_qr2_signature():
    service = _service()

    start_param = service.build_start_param(_entry())
    parsed = service.parse_start_param(start_param)

    assert start_param.startswith("t2_12_")
    assert parsed.code == "12"
    assert parsed.legacy is False


def test_tampered_numeric_start_parameter_is_rejected():
    service = _service()
    start_param = service.build_start_param(_entry())
    replacement = "0" if start_param[-1] != "0" else "1"

    with pytest.raises(InvalidTableEntry, match="Invalid table QR"):
        service.parse_start_param(start_param[:-1] + replacement)


def test_legacy_signed_qr_still_resolves_to_current_numeric_context():
    service = _service()
    start_param = service.build_legacy_start_param(TABLE_ID)

    resolution = service.resolve_start_param(start_param, [_entry()])

    assert start_param.startswith("t_")
    assert resolution.table_title == "Stol 12"
    assert resolution.manual_code == "12"


@pytest.mark.parametrize("code", ["12", "000012"])
def test_numeric_manual_code_normalizes_and_resolves(code):
    resolution = _service().resolve_manual_code(code, [_entry()])
    assert resolution.manual_code == "12"


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


def test_resolve_manual_code_returns_safe_table_context():
    service = _service()
    resolution = service.resolve_manual_code("12", [_entry()])

    assert resolution.table_title == "Stol 12"
    assert resolution.hall_title == "Asosiy zal"
    assert resolution.service_percent == Decimal("10")
    assert resolution.manual_code == "12"
    assert str(TABLE_ID) not in resolution.access_token
