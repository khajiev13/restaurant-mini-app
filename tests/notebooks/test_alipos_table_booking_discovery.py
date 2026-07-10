from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "alipos_table_booking_discovery.ipynb"

TEST_RESTAURANT_ID = "11111111-1111-4111-8111-111111111111"
DEPLOYED_RESTAURANT_ID = "22222222-2222-4222-8222-222222222222"
TEST_CASH_ORDER_ID = "33333333-3333-4333-8333-333333333333"
TEST_ONLINE_ORDER_ID = "44444444-4444-4444-8444-444444444444"
TEST_UUID_KEY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_UUID_V7 = "018f47a0-7b1c-7def-8abc-0123456789ab"

# Captured from the notebook's authentic saved dry run before live evidence replaced it.
AUTHENTIC_DRY_PROBE_OUTPUTS_JSON = r"""
[
  [{"name": "stdout", "output_type": "stream", "text": ["Configuration loaded; deployed target requires the second live-read flag.\n", "Live reads enabled: False\n", "Deployed reads enabled: False\n"]}],
  [{"name": "stdout", "output_type": "stream", "text": ["Offline safety self-checks passed.\n"]}],
  [{"name": "stdout", "output_type": "stream", "text": ["Dry run: authentication and all network requests are skipped.\n"]}],
  [{"name": "stdout", "output_type": "stream", "text": ["Dry run documented route names: ['restaurants', 'payment_methods', 'menu_composition', 'halls_and_tables']\n", "Dry run dummy-order route count: 4\n"]}],
  [{"name": "stdout", "output_type": "stream", "text": ["Dry run booking GET route count: 88\n"]}],
  [{"data": {"text/markdown": ["# AliPOS Table Booking Discovery\n", "\n", "**Mode:** dry run; no AliPOS API request was sent.\n", "\n", "Planned GET routes: 96\n", "\n", "Live execution requires both explicit AliPOS read flags."], "text/plain": ["<IPython.core.display.Markdown object>"]}, "metadata": {}, "output_type": "display_data"}]
]
"""

SAVED_STREAM_TEXT_CONTRACTS = {
    "dry": (
        r"Configuration loaded; deployed target requires the second live-read flag\.\n"
        r"Live reads enabled: False\nDeployed reads enabled: False\n",
        r"Offline safety self-checks passed\.\n",
        r"Dry run: authentication and all network requests are skipped\.\n",
        r"Dry run documented route names: \['restaurants', 'payment_methods', "
        r"'menu_composition', 'halls_and_tables'\]\n"
        r"Dry run dummy-order route count: 4\n",
        r"Dry run booking GET route count: [1-9][0-9]*\n",
    ),
    "live": (
        r"Configuration loaded; deployed target requires the second live-read flag\.\n"
        r"Live reads enabled: True\nDeployed reads enabled: True\n",
        r"Offline safety self-checks passed\.\n",
        r"AliPOS authentication succeeded; token output is suppressed\.\n",
        r"Documented and dummy-order GET probes completed\.\n",
        r"Booking discovery completed within request budget: ([0-9]+)\n",
    ),
}

OPPOSITE_MODE_MARKERS = {
    "dry": ("Live reads enabled: True", "Deployed reads enabled: True", "AliPOS authentication succeeded", "Documented and dummy-order GET probes completed", "Booking discovery completed", "**Mode:** live"),
    "live": ("Live reads enabled: False", "Deployed reads enabled: False", "Dry run", "**Mode:** dry run"),
}
SAVED_OUTPUT_PRIVACY_PATTERNS = (
    r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
    r"\+?998[0-9 ()-]{9,16}",
    r"(?i)\bBearer\s+",
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*(?![A-Za-z0-9_-])",
    r"(?i)\b(?:token|access[_-]?token|refresh[_-]?token|id[_-]?token|jwt|api[_-]?key|client[_-]?secret|password|credentials?)\b(?:\s*\[\s*[\\\"']*[A-Za-z0-9_-]+[\\\"']*\s*\])?[\\\"']*\s*(?::|=)",
)


def load_notebook() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def saved_probe_outputs(notebook: dict) -> list[list[dict]]:
    return [
        cell.get("outputs", [])
        for cell in notebook["cells"]
        if "probe-live" in cell.get("metadata", {}).get("tags", [])
    ]


def authentic_dry_probe_outputs() -> list[list[dict]]:
    return json.loads(AUTHENTIC_DRY_PROBE_OUTPUTS_JSON)


def authentic_live_probe_outputs() -> list[list[dict]]:
    return saved_probe_outputs(load_notebook())


def coherent_live_probe_outputs(request_count: int) -> list[list[dict]]:
    outputs = authentic_live_probe_outputs()
    outputs[4][0]["text"] = [
        f"Booking discovery completed within request budget: {request_count}\n"
    ]

    lines = outputs[5][0]["data"]["text/markdown"]
    route_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith(("| GET |", "| OPTIONS |"))
    ]
    route_rows = [lines[index] for index in route_indexes]
    selected_rows = (route_rows * 2)[:request_count]
    lines[route_indexes[0] : route_indexes[-1] + 1] = selected_rows

    for classification in (
        "confirmed",
        "unsupported",
        "unauthorized/forbidden",
        "invalid test data",
        "ambiguous",
        "skipped",
    ):
        index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(f"- {classification}:")
        )
        count = sum(f"| {classification} |" in row for row in selected_rows)
        lines[index] = f"- {classification}: {count}\n"
    return outputs


def inject_live_route_shape(outputs: list[list[dict]], payload: str) -> None:
    lines = outputs[5][0]["data"]["text/markdown"]
    index = next(index for index, line in enumerate(lines) if line.startswith("| GET |"))
    assert lines[index].endswith("` |\n")
    lines[index] = f"{lines[index][:-4]} {payload}` |\n"


def tamper_saved_probe_outputs(outputs: list[list[dict]], corruption: str) -> None:
    route_shape_injections = {
        "live-plus-one-dry-marker": "Dry run: authentication was skipped.",
        "email-injection": "operator@example.test",
        "opaque-token-field-injection": "access_token = opaque-value",
        "jwt-injection": "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjMifQ.",
        "signed-jwt-injection": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature",
        "bracket-credential-assignment": 'credentials["password"] = exposed-value',
    }
    if corruption in route_shape_injections:
        inject_live_route_shape(outputs, route_shape_injections[corruption])
    elif corruption == "dry-plus-one-live-marker":
        outputs[2][0]["text"].append(
            "AliPOS authentication succeeded; token output is suppressed.\n"
        )
    elif corruption == "missing-dry-report":
        outputs[5].clear()
    elif corruption == "appended-raw-body-output":
        outputs[3].append(
            {"name": "stdout", "output_type": "stream", "text": ['{"raw": true}\n']}
        )
    elif corruption == "unexpected-mime":
        outputs[5][0]["data"]["application/json"] = {"status": "ok"}
    elif corruption == "unexpected-output-type":
        outputs[5][0].update(output_type="execute_result", execution_count=11)
    elif corruption == "request-count-over-budget":
        outputs[4][0]["text"] = ["Booking discovery completed within request budget: 121\n"]
    elif corruption == "request-count-zero":
        outputs[4][0]["text"] = ["Booking discovery completed within request budget: 0\n"]
    elif corruption == "request-report-count-mismatch":
        outputs[4][0]["text"] = ["Booking discovery completed within request budget: 112\n"]
    elif corruption == "removed-route-row":
        lines = outputs[5][0]["data"]["text/markdown"]
        lines.pop(next(i for i, line in enumerate(lines) if line.startswith("| GET |")))
    elif corruption == "classification-total-mismatch":
        lines = outputs[5][0]["data"]["text/markdown"]
        index = next(i for i, line in enumerate(lines) if line.startswith("- confirmed:"))
        lines[index] = f"- confirmed: {int(lines[index].split(':')[1]) + 1}\n"
    else:
        raise AssertionError(f"unknown saved-output corruption: {corruption}")


def live_report_matches_contract(report: str, expected_route_count: int) -> bool:
    required_markers = (
        "# AliPOS Table Booking Discovery",
        "**Mode:** live read-only probe.",
        "## Classification counts",
        "## Route results",
        "| Method | Route | Status | Classification | Shape |",
        "## Conclusion",
        "Halls and tables alone do not confirm reservation support.",
    )
    classification_names = (
        "confirmed",
        "unsupported",
        "unauthorized/forbidden",
        "invalid test data",
        "ambiguous",
        "skipped",
    )
    counts = re.findall(
        r"^- (confirmed|unsupported|unauthorized/forbidden|invalid test data|ambiguous|skipped): ([0-9]+)$",
        report,
        re.MULTILINE,
    )
    route_rows = re.findall(
        r"^\| (?:GET|OPTIONS) \| `/[^`]+` \| (?:[1-5][0-9]{2}|network-error) \| "
        r"(?:confirmed|unsupported|unauthorized/forbidden|invalid test data|ambiguous|skipped) \| `.*` \|$",
        report,
        re.MULTILINE,
    )
    return (
        all(report.count(marker) == 1 for marker in required_markers)
        and tuple(name for name, _ in counts) == classification_names
        and len(route_rows) == sum(int(count) for _, count in counts) == expected_route_count
        and re.search(r"^\s*[\[{].*[\]}]\s*$", report, re.MULTILINE) is None
    )


def validate_saved_probe_outputs(outputs_by_cell: list[list[dict]]) -> str:
    assert isinstance(outputs_by_cell, list)
    assert len(outputs_by_cell) == 6
    assert all(
        isinstance(outputs, list) and len(outputs) == 1
        for outputs in outputs_by_cell
    )

    stream_texts = []
    for outputs in outputs_by_cell[:5]:
        output = outputs[0]
        assert isinstance(output, dict)
        assert set(output) == {"name", "output_type", "text"}
        assert output["name"] == "stdout"
        assert output["output_type"] == "stream"
        assert isinstance(output["text"], list)
        assert all(isinstance(line, str) for line in output["text"])
        stream_texts.append("".join(output["text"]))

    report_output = outputs_by_cell[5][0]
    assert isinstance(report_output, dict)
    assert set(report_output) == {"data", "metadata", "output_type"}
    assert report_output["output_type"] == "display_data"
    assert report_output["metadata"] == {}
    assert isinstance(report_output["data"], dict)
    assert set(report_output["data"]) == {"text/markdown", "text/plain"}
    assert report_output["data"]["text/plain"] == [
        "<IPython.core.display.Markdown object>"
    ]
    markdown_lines = report_output["data"]["text/markdown"]
    assert isinstance(markdown_lines, list)
    assert all(isinstance(line, str) for line in markdown_lines)
    report = "".join(markdown_lines)

    serialized = json.dumps(outputs_by_cell, ensure_ascii=False)
    assert all(
        re.search(pattern, serialized) is None
        for pattern in SAVED_OUTPUT_PRIVACY_PATTERNS
    )
    assert "secret" not in serialized.casefold()
    assert "error" not in serialized.casefold()
    assert all(
        output.get("output_type") != "error"
        for outputs in outputs_by_cell
        for output in outputs
    )

    dry_report = re.fullmatch(
        r"# AliPOS Table Booking Discovery\n\n"
        r"\*\*Mode:\*\* dry run; no AliPOS API request was sent\.\n\n"
        r"Planned GET routes: [1-9][0-9]*\n\n"
        r"Live execution requires both explicit AliPOS read flags\.",
        report,
    ) is not None
    dry_mode = dry_report and all(
        re.fullmatch(pattern, text) is not None
        for pattern, text in zip(SAVED_STREAM_TEXT_CONTRACTS["dry"], stream_texts)
    )
    live_contracts = SAVED_STREAM_TEXT_CONTRACTS["live"]
    live_count_match = re.fullmatch(live_contracts[4], stream_texts[4])
    live_request_count = int(live_count_match.group(1)) if live_count_match else 0
    live_mode = (
        live_count_match is not None
        and 1 <= live_request_count <= 120
        and all(
            re.fullmatch(pattern, text) is not None
            for pattern, text in zip(live_contracts[:4], stream_texts[:4])
        )
        and live_report_matches_contract(report, live_request_count)
    )
    mode_matches = [mode for mode, matches in (("dry", dry_mode), ("live", live_mode)) if matches]
    assert len(mode_matches) == 1

    mode = mode_matches[0]
    assert all(marker not in serialized for marker in OPPOSITE_MODE_MARKERS[mode])
    return mode


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

    live_cells = [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if "probe-live" in cell.get("metadata", {}).get("tags", [])
    ]
    assert len(live_cells) == 6
    ordered_responsibilities = (
        "CONFIG = build_probe_config(ROOT)",
        "_synthetic_config = dict(CONFIG)",
        "CLIENT = None",
        "HALL_ID = None",
        "BOOKING_CANDIDATES = build_booking_routes(",
        "REPORT = render_markdown_report(",
    )
    assert all(
        responsibility in source
        for responsibility, source in zip(ordered_responsibilities, live_cells)
    )


def test_notebook_introduction_describes_two_flag_deployed_authorization() -> None:
    notebook = load_notebook()
    introduction = "".join(notebook["cells"][0].get("source", []))

    assert "ALLOW_LIVE_ALIPOS_READS=1" in introduction
    assert "ALLOW_DEPLOYED_ALIPOS_READS=1" in introduction
    assert "both" in introduction.casefold()
    assert "block the deployed restaurant ID from all probes" not in introduction


def test_extract_dummy_identifiers_from_saved_cell_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.ipynb"
    write_source_notebook(source)
    namespace = load_probe_namespace()

    restaurant_id, order_ids = namespace["extract_dummy_identifiers"](source)

    assert restaurant_id == TEST_RESTAURANT_ID
    assert order_ids == (TEST_CASH_ORDER_ID, TEST_ONLINE_ORDER_ID)


def test_deployed_target_requires_second_live_flag_but_dry_run_is_allowed() -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config["dummy_restaurant_id"] = DEPLOYED_RESTAURANT_ID
    config["live_enabled"] = True
    config["deployed_reads_enabled"] = False

    namespace["validate_probe_config"](config, require_live=False)
    with pytest.raises(namespace["ProbeSafetyError"], match="explicit authorization"):
        namespace["validate_probe_config"](config, require_live=True)

    config["deployed_reads_enabled"] = True
    namespace["validate_probe_config"](config, require_live=True)


def test_validate_probe_config_requires_explicit_live_flag() -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config["live_enabled"] = False

    namespace["validate_probe_config"](config, require_live=False)
    with pytest.raises(namespace["LiveProbesDisabled"]):
        namespace["validate_probe_config"](config, require_live=True)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("timeout_seconds", 15.01),
        ("timeout_seconds", 0),
        ("timeout_seconds", -1),
        ("timeout_seconds", "15"),
        ("timeout_seconds", True),
        ("minimum_interval_seconds", 0.249),
        ("minimum_interval_seconds", 0),
        ("minimum_interval_seconds", -1),
        ("minimum_interval_seconds", "0.25"),
        ("minimum_interval_seconds", True),
        ("max_requests", 121),
        ("max_requests", 0),
        ("max_requests", -1),
        ("max_requests", 120.0),
        ("max_requests", "120"),
        ("max_requests", True),
    ],
)
def test_validate_probe_config_rejects_unsafe_http_limits(
    field: str,
    unsafe_value: object,
) -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config[field] = unsafe_value

    with pytest.raises(namespace["ProbeSafetyError"], match=field):
        namespace["validate_probe_config"](config)


def test_validate_probe_config_accepts_stricter_http_limits() -> None:
    namespace = load_probe_namespace()
    config = valid_config(namespace)
    config.update(
        timeout_seconds=7.5,
        minimum_interval_seconds=0.5,
        max_requests=60,
    )

    namespace["validate_probe_config"](config)


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


def test_documented_routes_match_vendor_documentation() -> None:
    namespace = load_probe_namespace()
    routes = namespace["build_documented_routes"](TEST_RESTAURANT_ID)
    assert [route["path"] for route in routes] == [
        "/restaurants",
        "/api/Integration/v1/paymentMethod/all",
        f"/api/Integration/v1/menu/{TEST_RESTAURANT_ID}/composition",
        f"/api/Integration/v1/restaurant/{TEST_RESTAURANT_ID}/halls-and-tables",
    ]
    assert all(route["method"] == "GET" for route in routes)


def test_booking_matrix_covers_every_term_and_is_unique() -> None:
    namespace = load_probe_namespace()
    hall_id = "55555555-5555-4555-8555-555555555555"
    table_id = "66666666-6666-4666-8666-666666666666"
    routes = namespace["build_booking_routes"](
        TEST_RESTAURANT_ID,
        hall_id=hall_id,
        table_id=table_id,
    )
    paths = [route["path"] for route in routes]

    assert len(paths) == len(set(paths))
    for term in namespace["BOOKING_TERMS"]:
        assert f"/api/Integration/v1/{term}" in paths
        assert f"/api/Integration/v1/restaurant/{TEST_RESTAURANT_ID}/{term}" in paths
        assert f"/api/Integration/v1/{term}/{TEST_RESTAURANT_ID}" in paths
        assert f"/api/Integration/v1/menu/{TEST_RESTAURANT_ID}/{term}" in paths
        assert f"/api/Integration/v1/{term}/{table_id}" in paths
        assert f"/api/Integration/v1/restaurant/{TEST_RESTAURANT_ID}/{term}/{table_id}" in paths
        assert f"/api/Integration/v1/{term}/{hall_id}" in paths
        assert f"/api/Integration/v1/restaurant/{TEST_RESTAURANT_ID}/{term}/{hall_id}" in paths


def test_get_selection_reserves_twelve_requests_for_options() -> None:
    namespace = load_probe_namespace()
    candidates = [
        {"name": f"route_{index}", "family": "top_level", "method": "GET", "path": f"/r/{index}"}
        for index in range(200)
    ]
    selected = namespace["select_get_routes"](candidates, completed_count=8)
    assert len(selected) == 100
    assert selected == candidates[:100]


def test_option_selection_prioritizes_405_then_one_404_per_family() -> None:
    namespace = load_probe_namespace()
    get_results = [
        {"name": "a", "family": "top_level", "method": "GET", "path": "/a", "status": 404},
        {"name": "b", "family": "top_level", "method": "GET", "path": "/b", "status": 404},
        {"name": "c", "family": "restaurant_scoped", "method": "GET", "path": "/c", "status": 404},
        {"name": "d", "family": "argument", "method": "GET", "path": "/d", "status": 405},
    ]
    selected = namespace["build_option_routes"](get_results, completed_count=116)
    assert [route["path"] for route in selected] == ["/d", "/a", "/c"]
    assert all(route["method"] == "OPTIONS" for route in selected)


from io import BytesIO
from urllib.error import HTTPError, URLError


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        url: str = "https://web.alipos.uz/api/Integration/v1/test",
        status: int = 200,
        headers=None,
    ) -> None:
        self._body = body
        self._url = url
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FailingReadResponse(FakeResponse):
    def read(self, size: int = -1) -> bytes:
        raise OSError("synthetic body read failure")


class FailingBytesIO(BytesIO):
    def read(self, size: int = -1) -> bytes:
        raise OSError("synthetic HTTPError body read failure")


def real_http_error(
    status: int,
    url: str = "https://web.alipos.uz/api/Integration/v1/test",
    body: bytes = b'{"error":"synthetic"}',
    body_stream=None,
) -> HTTPError:
    return HTTPError(
        url,
        status,
        "synthetic HTTP error",
        {"Content-Type": "application/json"},
        body_stream or BytesIO(body),
    )


class FakeOpener:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout: int):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_client_authenticates_then_sends_only_read_request() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [
            FakeResponse(b'{"access_token":"synthetic-access-token"}', url="https://web.alipos.uz/security/oauth/token"),
            FakeResponse(b'{"ok":true}'),
        ]
    )
    clock_values = iter([0.0, 0.0, 0.1, 0.2])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: next(clock_values),
    )

    client.authenticate()
    result = client.request("GET", "/api/Integration/v1/test", "test", "documented")

    assert opener.requests[0][0].get_method() == "POST"
    assert opener.requests[0][0].full_url.endswith("/security/oauth/token")
    assert opener.requests[1][0].get_method() == "GET"
    assert opener.requests[1][0].get_header("Authorization") == "Bearer synthetic-access-token"
    assert result["status"] == 200
    assert result["payload"] == {"ok": True}


def test_client_blocks_mutating_method_before_transport() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    with pytest.raises(namespace["UnsafeMethodError"], match="PUT"):
        client.request("PUT", "/api/Integration/v1/test", "test", "unsafe")
    assert opener.requests == []


def test_client_rejects_cross_origin_final_url() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [FakeResponse(b"{}", url="https://example.test/redirected")]
    )
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    with pytest.raises(namespace["UnsafeRedirectError"]):
        client.request("GET", "/api/Integration/v1/test", "test", "unsafe")


def test_discovery_rejects_cross_origin_http_error_before_body_read() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [
            real_http_error(
                404,
                url="https://example.test/redirected",
                body_stream=FailingBytesIO(b"synthetic"),
            )
        ]
    )
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    with pytest.raises(namespace["UnsafeRedirectError"]):
        client.request("GET", "/api/Integration/v1/test", "test", "unsafe")
    assert len(opener.requests) == 1


def test_authentication_rejects_cross_origin_http_error() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [
            real_http_error(
                401,
                url="https://example.test/security/oauth/token",
                body_stream=FailingBytesIO(b"synthetic"),
            )
        ]
    )
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )

    with pytest.raises(namespace["UnsafeRedirectError"]):
        client.authenticate()
    assert len(opener.requests) == 1


def test_client_decodes_same_origin_real_urllib_http_error() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([real_http_error(404, body=b'{"error":"missing"}')])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    result = client.request(
        "GET",
        "/api/Integration/v1/test",
        "test",
        "documented",
    )

    assert result["status"] == 404
    assert result["payload"] == {"error": "missing"}
    assert result["classification"] == "unsupported"


def test_client_does_not_retry_transport_failure() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([URLError("synthetic failure")])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    result = client.request("GET", "/api/Integration/v1/test", "test", "documented")

    assert len(opener.requests) == 1
    assert result["status"] is None
    assert result["classification"] == "ambiguous"


def test_client_stops_all_later_requests_after_rate_limit() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [
            FakeResponse(b'{"error":"rate limited"}', status=429),
            FakeResponse(b'{"ok":true}'),
        ]
    )
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    result = client.request("GET", "/api/Integration/v1/a", "a", "top_level")
    assert result["status"] == 429
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.request("GET", "/api/Integration/v1/b", "b", "top_level")
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.authenticate()
    assert len(opener.requests) == 1


def test_rate_limit_stop_precedes_authentication_requirement() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([FakeResponse(b"{}", status=429)])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    client.request("GET", "/api/Integration/v1/a", "a", "top_level")
    client._access_token = None

    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.request("GET", "/api/Integration/v1/b", "b", "top_level")
    assert len(opener.requests) == 1


def test_discovery_429_latches_before_ordinary_body_read_failure() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([FailingReadResponse(b"", status=429)])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    with pytest.raises(OSError, match="body read failure"):
        client.request("GET", "/api/Integration/v1/a", "a", "top_level")

    assert client.rate_limited is True
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.authenticate()
    assert len(opener.requests) == 1


def test_discovery_http_error_429_latches_before_body_read_failure() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener(
        [real_http_error(429, body_stream=FailingBytesIO(b"synthetic"))]
    )
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    client._access_token = "synthetic-access-token"

    with pytest.raises(OSError, match="HTTPError body read failure"):
        client.request("GET", "/api/Integration/v1/a", "a", "top_level")

    assert client.rate_limited is True
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.authenticate()
    assert len(opener.requests) == 1


def test_authentication_http_error_429_permanently_stops_transport() -> None:
    namespace = load_probe_namespace()
    opener = FakeOpener([real_http_error(429)])
    client = namespace["SafeAliPOSClient"](
        valid_config(namespace),
        opener=opener,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )

    with pytest.raises(namespace["AuthenticationError"], match="429"):
        client.authenticate()

    assert client.rate_limited is True
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.authenticate()
    with pytest.raises(namespace["RequestBudgetExceeded"], match="rate limit"):
        client.request("GET", "/api/Integration/v1/a", "a", "top_level")
    assert len(opener.requests) == 1


def test_rendered_report_contains_no_raw_sensitive_values() -> None:
    namespace = load_probe_namespace()
    result = {
        "name": "halls_and_tables",
        "family": "documented",
        "method": "GET",
        "path": f"/api/Integration/v1/restaurant/{TEST_RESTAURANT_ID}/halls-and-tables",
        "status": 200,
        "latency_ms": 12.3,
        "content_type": "application/json",
        "allow": "GET",
        "payload": {
            "Halls": [{"Id": TEST_RESTAURANT_ID, "Title": "Test Hall", "phoneNumber": "+998901234567"}],
            "Tables": [],
        },
        "error": "",
    }

    report = namespace["render_markdown_report"]([result])

    assert "# AliPOS Table Booking Discovery" in report
    assert "confirmed" in report
    assert TEST_RESTAURANT_ID not in report
    assert "+998901234567" not in report
    assert "Halls and tables alone do not confirm reservation support." in report


def test_rendered_report_redacts_uuid_shaped_mapping_keys() -> None:
    namespace = load_probe_namespace()
    result = {
        "name": "unknown_shape",
        "family": "top_level",
        "method": "GET",
        "path": "/api/Integration/v1/unknown",
        "status": 200,
        "latency_ms": 1.0,
        "content_type": "application/json",
        "allow": "GET",
        "payload": {TEST_UUID_KEY: [{TEST_UUID_KEY: "safe"}]},
        "error": "",
    }

    report = namespace["render_markdown_report"]([result])

    assert TEST_UUID_KEY not in report


def test_rendered_report_redacts_uuidv7_values_and_paths() -> None:
    namespace = load_probe_namespace()
    result = {
        "name": "halls_and_tables",
        "family": "documented",
        "method": "GET",
        "path": f"/api/Integration/v1/restaurant/{TEST_UUID_V7}/halls-and-tables",
        "status": 200,
        "latency_ms": 1.0,
        "content_type": "application/json",
        "allow": "GET",
        "payload": {
            "Halls": [{"Id": TEST_UUID_V7, "Title": "Test Hall", "ServicePercent": 12}],
            "Tables": [],
        },
        "error": "",
    }

    report = namespace["render_markdown_report"]([result])

    assert TEST_UUID_V7 not in report


def test_halls_and_tables_report_redacts_non_numeric_service_percent() -> None:
    namespace = load_probe_namespace()
    result = {
        "name": "halls_and_tables",
        "family": "documented",
        "method": "GET",
        "path": "/api/Integration/v1/restaurant/test/halls-and-tables",
        "status": 200,
        "latency_ms": 1.0,
        "content_type": "application/json",
        "allow": "GET",
        "payload": {
            "Halls": [
                {
                    "Id": TEST_RESTAURANT_ID,
                    "Title": "Test Hall",
                    "ServicePercent": "+998901234567",
                }
            ],
            "Tables": [],
        },
        "error": "",
    }

    report = namespace["render_markdown_report"]([result])

    assert "+998901234567" not in report
    assert '"servicePercent": "[REDACTED]"' in report
    assert "Test Hall" in report


def test_live_cells_end_in_safe_outputs_and_do_not_display_raw_objects() -> None:
    notebook = load_notebook()
    live_sources = [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if "probe-live" in cell.get("metadata", {}).get("tags", [])
    ]

    def terminal_statements(statements: list[ast.stmt]) -> list[ast.stmt]:
        terminal = statements[-1]
        if isinstance(terminal, ast.If):
            return terminal_statements(terminal.body) + terminal_statements(terminal.orelse)
        return [terminal]

    forbidden_raw_names = {"CONFIG", "CLIENT", "RESULTS", "payload", "access_token"}
    for source in live_sources:
        tree = ast.parse(source)
        for terminal in terminal_statements(tree.body):
            assert isinstance(terminal, ast.Expr)
            assert isinstance(terminal.value, ast.Call)
            assert isinstance(terminal.value.func, ast.Name)
            assert terminal.value.func.id in {"display", "print"}

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"display", "print"}:
                continue
            assert all(
                not isinstance(argument, ast.Name) or argument.id not in forbidden_raw_names
                for argument in node.args
            )


@pytest.mark.parametrize(
    ("expected_mode", "outputs_factory"),
    (
        pytest.param("dry", authentic_dry_probe_outputs, id="authentic-dry"),
        pytest.param("live", authentic_live_probe_outputs, id="authentic-live"),
    ),
)
def test_saved_output_contract_accepts_complete_authentic_mode(
    expected_mode: str,
    outputs_factory,
) -> None:
    assert validate_saved_probe_outputs(outputs_factory()) == expected_mode


@pytest.mark.parametrize("request_count", (1, 120), ids=("minimum", "maximum"))
def test_saved_output_contract_accepts_live_request_count_boundaries(
    request_count: int,
) -> None:
    outputs = coherent_live_probe_outputs(request_count)

    assert validate_saved_probe_outputs(outputs) == "live"


@pytest.mark.parametrize(
    ("base_mode", "corruption"),
    (
        pytest.param("dry", "missing-dry-report", id="missing-dry-report"),
        pytest.param("live", "live-plus-one-dry-marker", id="live-plus-one-dry-marker"),
        pytest.param("dry", "dry-plus-one-live-marker", id="dry-plus-one-live-marker"),
        pytest.param("live", "email-injection", id="email-injection"),
        pytest.param("live", "opaque-token-field-injection", id="opaque-token-field-injection"),
        pytest.param("live", "jwt-injection", id="jwt-injection"),
        pytest.param("live", "signed-jwt-injection", id="signed-jwt-injection"),
        pytest.param("live", "bracket-credential-assignment", id="bracket-credential-assignment"),
        pytest.param("live", "appended-raw-body-output", id="appended-raw-body-output"),
        pytest.param("live", "unexpected-mime", id="unexpected-mime"),
        pytest.param("live", "unexpected-output-type", id="unexpected-output-type"),
        pytest.param("live", "request-count-over-budget", id="request-count-over-budget"),
        pytest.param("live", "request-count-zero", id="request-count-zero"),
        pytest.param("live", "request-report-count-mismatch", id="request-report-count-mismatch"),
        pytest.param("live", "removed-route-row", id="removed-route-row"),
        pytest.param("live", "classification-total-mismatch", id="classification-total-mismatch"),
    ),
)
def test_saved_output_contract_rejects_tampered_artifacts(
    base_mode: str,
    corruption: str,
) -> None:
    outputs = (
        authentic_dry_probe_outputs()
        if base_mode == "dry"
        else authentic_live_probe_outputs()
    )
    tamper_saved_probe_outputs(outputs, corruption)

    with pytest.raises(AssertionError):
        validate_saved_probe_outputs(outputs)


def test_saved_outputs_use_one_safe_authentic_mode() -> None:
    outputs_by_cell = saved_probe_outputs(load_notebook())

    assert validate_saved_probe_outputs(outputs_by_cell) in {"dry", "live"}


def test_notebook_constructs_exactly_one_oauth_post() -> None:
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )

    assert source.count('self._build_url("/security/oauth/token")') == 1
    assert len(re.findall(r"method\s*=\s*['\"]POST['\"]", source)) == 1


def test_live_cells_do_not_call_mutating_discovery_methods() -> None:
    notebook = load_notebook()
    live_source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if "probe-live" in cell.get("metadata", {}).get("tags", [])
    )
    forbidden = re.compile(r"\.request\(\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]")
    assert forbidden.search(live_source) is None
    assert "/api/Integration/v1/order\"" not in live_source
