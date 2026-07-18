import datetime
import re
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
def test_manual_code_rejects_missing_or_oversized_trailing_number(title):
    with pytest.raises(InvalidTableDirectory):
        manual_code_from_title(title)


@pytest.mark.asyncio
async def test_directory_accepts_numeric_gaps_including_missing_nine():
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 8", "hallId": str(HALL_ID)},
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "title": "Stoll 10",
                "hallId": str(HALL_ID),
            },
        ],
    }
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        directory = await get_table_directory()
    assert [entry.manual_code for entry in directory] == ["8", "10"]


@pytest.mark.asyncio
async def test_directory_rejects_duplicate_numeric_codes_across_halls():
    other_hall_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
            {"id": str(other_hall_id), "title": "Terrace", "servicePercent": 15},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 12", "hallId": str(HALL_ID)},
            {
                "id": "44444444-4444-4444-8444-444444444444",
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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.__setitem__("halls", {}),
        lambda payload: payload.__setitem__("tables", {}),
        lambda payload: payload["halls"].__setitem__(0, "not-an-object"),
        lambda payload: payload["halls"][0].__setitem__("id", "not-a-uuid"),
        lambda payload: payload["halls"].append(dict(payload["halls"][0])),
        lambda payload: payload["tables"].__setitem__(0, "not-an-object"),
        lambda payload: payload["tables"][0].__setitem__("id", "not-a-uuid"),
        lambda payload: payload["tables"].append(
            {
                **payload["tables"][0],
                "title": "Stoll 13",
            }
        ),
        lambda payload: payload["tables"][0].__setitem__(
            "hallId", "55555555-5555-4555-8555-555555555555"
        ),
    ],
    ids=[
        "halls-not-array",
        "tables-not-array",
        "hall-not-object",
        "malformed-hall-id",
        "duplicate-hall-id",
        "table-not-object",
        "malformed-table-id",
        "duplicate-table-id",
        "unknown-hall-id",
    ],
)
@pytest.mark.asyncio
async def test_directory_rejects_malformed_or_ambiguous_records(mutate):
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 12", "hallId": str(HALL_ID)},
        ],
    }
    mutate(payload)
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(InvalidTableDirectory):
            await get_table_directory()


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
