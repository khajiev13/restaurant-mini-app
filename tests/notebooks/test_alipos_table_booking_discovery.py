from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "alipos_table_booking_discovery.ipynb"

TEST_RESTAURANT_ID = "11111111-1111-4111-8111-111111111111"
DEPLOYED_RESTAURANT_ID = "22222222-2222-4222-8222-222222222222"
TEST_CASH_ORDER_ID = "33333333-3333-4333-8333-333333333333"
TEST_ONLINE_ORDER_ID = "44444444-4444-4444-8444-444444444444"


def load_notebook() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def load_probe_namespace() -> dict:
    notebook = load_notebook()
    namespace = {"__name__": "alipos_table_booking_discovery"}
    for index, cell in enumerate(notebook["cells"], start=1):
        tags = cell.get("metadata", {}).get("tags", [])
        if cell.get("cell_type") != "code" or "probe-library" not in tags:
            continue
        source = "".join(cell.get("source", []))
        exec(compile(source, f"{NOTEBOOK}:cell-{index}", "exec"), namespace)
    return namespace


def write_source_notebook(path: Path) -> None:
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["unused"],
        }
        for _ in range(10)
    ]
    cells[3] = {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [
            {
                "name": "stdout",
                "output_type": "stream",
                "text": [
                    f"Restaurant ID: {TEST_RESTAURANT_ID}\n",
                    "CREATE_TEST_ORDERS: True\n",
                ],
            }
        ],
        "source": [],
    }
    cells[9] = {
        "cell_type": "code",
        "execution_count": 2,
        "metadata": {},
        "outputs": [
            {
                "name": "stdout",
                "output_type": "stream",
                "text": [
                    "ID созданных заказов / Yaratilgan buyurtma ID lari:\n",
                    "{\n",
                    f'  "cash": "{TEST_CASH_ORDER_ID}",\n',
                    f'  "online-order": "{TEST_ONLINE_ORDER_ID}"\n',
                    "}\n",
                ],
            }
        ],
        "source": [],
    }
    path.write_text(
        json.dumps(
            {
                "cells": cells,
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )


def valid_config(namespace: dict) -> dict:
    return {
        "base_url": "https://web.alipos.uz",
        "client_id": "synthetic-client-id",
        "client_secret": "synthetic-client-secret",
        "deployed_restaurant_id": DEPLOYED_RESTAURANT_ID,
        "dummy_restaurant_id": TEST_RESTAURANT_ID,
        "dummy_order_ids": (TEST_CASH_ORDER_ID, TEST_ONLINE_ORDER_ID),
        "live_enabled": True,
        "timeout_seconds": 15,
        "minimum_interval_seconds": 0.25,
        "max_requests": 120,
    }


def test_notebook_has_expected_tagged_layout() -> None:
    notebook = load_notebook()
    assert notebook["nbformat"] == 4
    assert notebook["nbformat_minor"] == 5
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"
    tags = {
        tag
        for cell in notebook["cells"]
        for tag in cell.get("metadata", {}).get("tags", [])
    }
    assert "probe-library" in tags
    assert "probe-live" in tags


def test_extract_dummy_identifiers_from_saved_cell_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.ipynb"
    write_source_notebook(source)
    namespace = load_probe_namespace()

    restaurant_id, order_ids = namespace["extract_dummy_identifiers"](source)

    assert restaurant_id == TEST_RESTAURANT_ID
    assert order_ids == (TEST_CASH_ORDER_ID, TEST_ONLINE_ORDER_ID)


def test_validate_probe_config_rejects_deployed_restaurant_id() -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config["dummy_restaurant_id"] = DEPLOYED_RESTAURANT_ID

    with pytest.raises(namespace["ProbeSafetyError"], match="deployed"):
        namespace["validate_probe_config"](config)


def test_validate_probe_config_requires_explicit_live_flag() -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config["live_enabled"] = False

    namespace["validate_probe_config"](config, require_live=False)
    with pytest.raises(namespace["LiveProbesDisabled"]):
        namespace["validate_probe_config"](config, require_live=True)


def test_redaction_removes_sensitive_values_and_masks_identifiers() -> None:
    namespace = load_probe_namespace()
    payload = {
        "access_token": "synthetic-token-value",
        "phoneNumber": "+998901234567",
        "deliveryAddress": "Synthetic street 10",
        "customer": {
            "email": "person@example.test",
            "id": TEST_CASH_ORDER_ID,
        },
        "title": "Main Hall",
    }

    redacted = namespace["redact_value"](payload)
    serialized = json.dumps(redacted, ensure_ascii=False)

    assert "synthetic-token-value" not in serialized
    assert "+998901234567" not in serialized
    assert "Synthetic street 10" not in serialized
    assert "person@example.test" not in serialized
    assert TEST_CASH_ORDER_ID not in serialized
    assert redacted["title"] == "Main Hall"
    assert redacted["customer"]["id"].startswith("id:")


def test_recursive_redaction_covers_extended_privacy_key_families() -> None:
    namespace = load_probe_namespace()
    sensitive_values = {
        "client_id": "private-client-id",
        "credentials": {"username": "private-user"},
        "customerName": "Private Customer",
        "payment": {"provider": "private-provider"},
        "number": "private-number",
        "card-number": "4111111111111111",
        "CVV": "123",
        "lat": 41.3111,
        "lng": 69.2401,
        "coordinates": [41.3111, 69.2401],
    }
    payload = {"outer": [{"private": sensitive_values}]}

    redacted = namespace["redact_value"](payload)

    assert redacted["outer"][0]["private"] == {
        key: "[REDACTED]" for key in sensitive_values
    }


def test_sensitive_key_matching_keeps_safe_fields_and_fingerprints_uuid() -> None:
    namespace = load_probe_namespace()
    payload = {
        "platform": "web",
        "company": "AliPOS",
        "hall": {
            "title": "Main Hall",
            "servicePercent": 12,
            "id": TEST_CASH_ORDER_ID,
        },
        "table": {
            "title": "T-1",
            "id": TEST_ONLINE_ORDER_ID,
        },
    }

    redacted = namespace["redact_value"](payload)

    assert redacted == {
        "platform": "web",
        "company": "AliPOS",
        "hall": {
            "title": "Main Hall",
            "servicePercent": 12,
            "id": namespace["fingerprint_identifier"](TEST_CASH_ORDER_ID),
        },
        "table": {
            "title": "T-1",
            "id": namespace["fingerprint_identifier"](TEST_ONLINE_ORDER_ID),
        },
    }


def test_halls_and_tables_summary_keeps_only_safe_fields() -> None:
    namespace = load_probe_namespace()
    hall_id = "55555555-5555-4555-8555-555555555555"
    table_id = "66666666-6666-4666-8666-666666666666"
    payload = {
        "Halls": [
            {
                "Id": hall_id,
                "Title": "Test Hall",
                "ServicePercent": 12,
                "phoneNumber": "+998901234567",
            }
        ],
        "Tables": [
            {
                "Id": table_id,
                "Title": "T-1",
                "HallId": hall_id,
                "clientName": "Synthetic Person",
            }
        ],
    }

    summary = namespace["summarize_payload"](payload, "halls_and_tables")
    selected_hall, selected_table = namespace["extract_hall_table_ids"](payload)
    serialized = json.dumps(summary, ensure_ascii=False)

    assert selected_hall == hall_id
    assert selected_table == table_id
    assert summary["collections"]["Halls"]["count"] == 1
    assert summary["collections"]["Tables"]["count"] == 1
    assert summary["preview"]["halls"][0]["title"] == "Test Hall"
    assert summary["preview"]["halls"][0]["servicePercent"] == 12
    assert summary["preview"]["tables"][0]["title"] == "T-1"
    assert "Test Hall" in serialized
    assert hall_id not in serialized
    assert table_id not in serialized
    assert "+998901234567" not in serialized
    assert "Synthetic Person" not in serialized


@pytest.mark.parametrize(
    ("status", "content_type", "allow", "expected"),
    [
        (200, "application/json", "", "confirmed"),
        (404, "application/json", "", "unsupported"),
        (405, "application/json", "POST", "unsupported"),
        (401, "application/json", "", "unauthorized/forbidden"),
        (422, "application/json", "", "invalid test data"),
        (500, "text/html", "", "ambiguous"),
    ],
)
def test_result_classification(
    status: int,
    content_type: str,
    allow: str,
    expected: str,
) -> None:
    namespace = load_probe_namespace()
    result = {
        "status": status,
        "content_type": content_type,
        "allow": allow,
        "payload": {} if "json" in content_type else None,
        "error": "",
    }
    assert namespace["classify_result"](result) == expected


def test_result_summary_replaces_arbitrary_errors_with_a_generic_marker() -> None:
    namespace = load_probe_namespace()
    private_detail = "synthetic-internal-detail"
    errors = [
        f"Upstream failure: {private_detail}",
        {"message": private_detail},
        [private_detail],
    ]

    summaries = [
        namespace["summarize_result"](
            {
                "status": 500,
                "content_type": "text/plain",
                "payload": None,
                "error": error,
            }
        )
        for error in errors
    ]

    assert [summary["error"] for summary in summaries] == ["[REDACTED]"] * len(errors)
    assert all(private_detail not in json.dumps(summary) for summary in summaries)
    assert namespace["summarize_result"]({"error": ""})["error"] == ""
