import datetime
from unittest.mock import AsyncMock

import pytest

from app.services import alipos_api

DIRECTORY = {
    "halls": [
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "title": "Main",
            "servicePercent": 10,
        }
    ],
    "tables": [
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "title": "Stol 1",
            "hallId": "22222222-2222-4222-8222-222222222222",
        }
    ],
}


class JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def reset_table_cache(monkeypatch):
    monkeypatch.setattr(alipos_api, "_tables_cache", None)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", None)


@pytest.mark.asyncio
async def test_halls_tables_snapshot_records_fresh_success(monkeypatch):
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(DIRECTORY)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is False
    assert snapshot.last_success_at.tzinfo == datetime.UTC


@pytest.mark.asyncio
async def test_halls_tables_snapshot_reuses_fresh_cache_without_provider_call(
    monkeypatch,
):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    request = AsyncMock()
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", float("inf"))
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(alipos_api, "_api_request", request)

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.stale is False
    assert snapshot.last_success_at == last_success
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_halls_tables_snapshot_returns_stale_cache_after_refresh_error(
    monkeypatch,
):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True
    assert snapshot.last_success_at == last_success


@pytest.mark.asyncio
async def test_halls_tables_snapshot_uses_stale_cache_for_malformed_success(
    monkeypatch,
):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse({"halls": "not-a-list", "tables": []})),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True


@pytest.mark.parametrize(
    "malformed",
    [
        {
            "halls": [{"id": "not-a-uuid", "title": "Broken", "servicePercent": 10}],
            "tables": [],
        },
        {
            "halls": DIRECTORY["halls"],
            "tables": [
                {
                    "id": "not-a-uuid",
                    "title": "Broken",
                    "hallId": DIRECTORY["halls"][0]["id"],
                }
            ],
        },
        {
            "halls": DIRECTORY["halls"],
            "tables": [
                {
                    "id": "44444444-4444-4444-8444-444444444444",
                    "title": "Orphan",
                    "hallId": "55555555-5555-4555-8555-555555555555",
                }
            ],
        },
    ],
)
@pytest.mark.asyncio
async def test_malformed_row_never_replaces_last_complete_directory(
    monkeypatch, malformed
):
    last_success = datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(alipos_api, "_tables_cache_last_success_at", last_success)
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(malformed)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == DIRECTORY
    assert snapshot.stale is True
    assert snapshot.last_success_at == last_success


@pytest.mark.asyncio
async def test_malformed_row_raises_when_no_complete_directory_exists(monkeypatch):
    malformed = {
        "halls": DIRECTORY["halls"],
        "tables": [
            {
                "id": "not-a-uuid",
                "title": "Broken",
                "hallId": DIRECTORY["halls"][0]["id"],
            }
        ],
    }
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(malformed)),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables_snapshot()


@pytest.mark.asyncio
async def test_halls_tables_snapshot_raises_without_any_cache(monkeypatch):
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables_snapshot()


@pytest.mark.asyncio
async def test_empty_halls_tables_directory_is_a_valid_fresh_success(monkeypatch):
    empty = {"halls": [], "tables": []}
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(return_value=JsonResponse(empty)),
    )

    snapshot = await alipos_api.get_halls_and_tables_snapshot()

    assert snapshot.payload == empty
    assert snapshot.stale is False


@pytest.mark.asyncio
async def test_legacy_customer_directory_rejects_stale_fallback(monkeypatch):
    monkeypatch.setattr(alipos_api, "_tables_cache", DIRECTORY)
    monkeypatch.setattr(alipos_api, "_tables_cache_expires_at", 0.0)
    monkeypatch.setattr(
        alipos_api,
        "_tables_cache_last_success_at",
        datetime.datetime(2026, 7, 15, 9, 0, tzinfo=datetime.UTC),
    )
    monkeypatch.setattr(
        alipos_api,
        "_api_request",
        AsyncMock(side_effect=RuntimeError("AliPOS unavailable")),
    )

    with pytest.raises(alipos_api.HallsTablesUnavailable):
        await alipos_api.get_halls_and_tables()
