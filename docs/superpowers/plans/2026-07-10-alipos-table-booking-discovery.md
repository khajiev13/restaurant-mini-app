# AliPOS Table Booking Discovery Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a safe AliPOS notebook that verifies documented hall/table reads and probes booking-related GET routes with saved test-order IDs.

**Architecture:** Keep the implementation in one self-contained `.ipynb`. Pure helpers live in code cells tagged `probe-library`; an offline pytest harness loads only those cells, so safety, redaction, routing, and HTTP behavior can be tested without executing configuration or live-network cells. Live cells authenticate with the official `.env` credentials, require two explicit flags before reading the deployed restaurant, run only `GET`/`OPTIONS` after OAuth, and render sanitized results.

**Tech Stack:** Python 3.9 standard library (`json`, `urllib`, `hashlib`, `re`, `time`), nbformat 4.5 JSON, pytest 8.4.2 through `/usr/bin/python3`, and ephemeral `uv` packages (`nbconvert`, `ipykernel`) for notebook execution.

## Global Constraints

- Read the approved design first: `docs/superpowers/specs/2026-07-10-alipos-table-booking-discovery-design.md`.
- Work in the current checkout. Do not create a worktree: the source test notebook is untracked and exists only in this workspace.
- Load official AliPOS authentication values from the ignored project `.env`; never display or persist them.
- The saved test restaurant ID equals `.env`'s deployed restaurant ID. The user explicitly authorized read-only deployed probes on 2026-07-10.
- Require both `ALLOW_LIVE_ALIPOS_READS=1` and `ALLOW_DEPLOYED_ALIPOS_READS=1` before any deployed request. Both flags remain off in the saved notebook and dry run.
- Extract the target restaurant and test-order IDs only from saved cells 4 and 10 of `notebooks/alipos_support_report_ru_uz.ipynb`; never execute that notebook.
- Permit exactly one mutating-method request: OAuth `POST /security/oauth/token`. After authentication, allow only `GET` and `OPTIONS`.
- Keep both live-read flags off by default; only the explicitly approved live execution process may set them to `1`.
- Run requests sequentially, wait at least 250 milliseconds between them, use a 15-second timeout, make no retries, and cap post-authentication requests at 120 including `OPTIONS`.
- Reject redirects and any URL whose origin differs from the configured AliPOS origin.
- Keep raw payloads in kernel memory only. Notebook outputs may contain only sanitized summaries.
- Use Python 3.9-compatible syntax; do not use `X | None` type unions.
- Do not modify existing notebooks, backend code, `.env`, or AliPOS documentation notes.
- Never stage `notebooks/` as a directory. Stage only the new notebook and its test file by exact path.

## File Structure

- Create `notebooks/alipos_table_booking_discovery.ipynb`: configuration, pure helpers, self-checks, live orchestration, and sanitized report.
- Create `tests/notebooks/test_alipos_table_booking_discovery.py`: offline tests that load tagged notebook helper cells without making network requests.
- Do not modify any other file during implementation.

---

### Task 1: Safe notebook scaffold, dummy-ID extraction, and configuration guards

**Files:**
- Create: `notebooks/alipos_table_booking_discovery.ipynb`
- Create: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Produces: `LIVE_FLAG_NAME`, `UUID_RE`, `ProbeSafetyError`, `LiveProbesDisabled`, `find_repo_root(start=None)`, `read_dotenv(path)`, `extract_dummy_identifiers(source_notebook)`, `build_probe_config(repo_root, environ=None)`, and `validate_probe_config(config, require_live=True)`.
- Consumes: saved stream output from cells 4 and 10 of `notebooks/alipos_support_report_ru_uz.ipynb` and official key/value pairs from `.env`.

- [ ] **Step 1: Write the failing notebook-loader and configuration tests**

Create `tests/notebooks/test_alipos_table_booking_discovery.py` with this initial content:

```python
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
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: FAIL with `FileNotFoundError` for `notebooks/alipos_table_booking_discovery.ipynb`.

- [ ] **Step 3: Create the notebook shell and configuration library cell**

Use `apply_patch` to add a valid nbformat 4.5 notebook. Set this metadata:

```json
{
  "kernelspec": {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3"
  },
  "language_info": {
    "name": "python",
    "version": "3.9.6"
  }
}
```

Add a first Markdown cell explaining that the notebook is read-only, uses official credentials only for authentication, and blocks the deployed restaurant ID.

Add a code cell tagged `probe-library` with this complete source:

```python
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple
from urllib.parse import urlsplit


LIVE_FLAG_NAME = "ALLOW_LIVE_ALIPOS_READS"
UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
UUID_RE = re.compile(rf"^{UUID_PATTERN}$")


class ProbeSafetyError(RuntimeError):
    pass


class LiveProbesDisabled(ProbeSafetyError):
    pass


def find_repo_root(start: Optional[Path] = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").is_file() and (candidate / "notebooks").is_dir():
            return candidate
    raise ProbeSafetyError("Repository root with .env and notebooks was not found")


def read_dotenv(path: Path) -> dict:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _stream_output_text(cell: Mapping[str, Any]) -> str:
    parts = []
    for output in cell.get("outputs", []):
        text = output.get("text", "")
        if isinstance(text, list):
            parts.extend(str(item) for item in text)
        elif text:
            parts.append(str(text))
    return "".join(parts)


def extract_dummy_identifiers(source_notebook: Path) -> Tuple[str, Tuple[str, ...]]:
    document = json.loads(source_notebook.read_text(encoding="utf-8"))
    cells = document.get("cells", [])
    if len(cells) < 10:
        raise ProbeSafetyError("Source notebook does not contain cells 4 and 10")

    config_output = _stream_output_text(cells[3])
    restaurant_match = re.search(rf"Restaurant ID:\s*({UUID_PATTERN})", config_output)
    if restaurant_match is None:
        raise ProbeSafetyError("Dummy restaurant ID was not found in source cell 4")

    created_output = _stream_output_text(cells[9])
    marker = "ID созданных заказов / Yaratilgan buyurtma ID lari:"
    if marker not in created_output:
        raise ProbeSafetyError("Dummy order marker was not found in source cell 10")
    tail = created_output.split(marker, 1)[1].lstrip()
    try:
        order_map, _ = json.JSONDecoder().raw_decode(tail)
    except (TypeError, ValueError) as exc:
        raise ProbeSafetyError("Dummy order map in source cell 10 is invalid") from exc

    order_ids = tuple(order_map.get(name, "") for name in ("cash", "online-order"))
    if any(not UUID_RE.fullmatch(value) for value in order_ids):
        raise ProbeSafetyError("Source cell 10 does not contain two valid dummy order IDs")
    return restaurant_match.group(1), order_ids


def build_probe_config(
    repo_root: Path,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    dotenv = read_dotenv(repo_root / ".env")
    process = dict(os.environ if environ is None else environ)

    def configured(name: str) -> str:
        return process.get(name) or dotenv.get(name, "")

    dummy_restaurant_id, dummy_order_ids = extract_dummy_identifiers(
        repo_root / "notebooks" / "alipos_support_report_ru_uz.ipynb"
    )
    return {
        "base_url": configured("ALIPOS_API_BASE_URL").rstrip("/"),
        "client_id": configured("ALIPOS_API_CLIENT_ID"),
        "client_secret": configured("ALIPOS_API_CLIENT_SECRET"),
        "deployed_restaurant_id": configured("ALIPOS_RESTAURANT_ID"),
        "dummy_restaurant_id": dummy_restaurant_id,
        "dummy_order_ids": dummy_order_ids,
        "live_enabled": process.get(LIVE_FLAG_NAME) == "1",
        "timeout_seconds": 15,
        "minimum_interval_seconds": 0.25,
        "max_requests": 120,
    }


def validate_probe_config(
    config: Mapping[str, Any],
    require_live: bool = True,
) -> None:
    required = (
        "base_url",
        "client_id",
        "client_secret",
        "deployed_restaurant_id",
        "dummy_restaurant_id",
    )
    missing = [name for name in required if not str(config.get(name, "")).strip()]
    if missing:
        raise ProbeSafetyError("Required AliPOS configuration is missing")

    parsed = urlsplit(str(config["base_url"]))
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise ProbeSafetyError("AliPOS base URL must use HTTPS")
    if hostname != "alipos.uz" and not hostname.endswith(".alipos.uz"):
        raise ProbeSafetyError("Configured host is not an AliPOS host")
    if parsed.username or parsed.password:
        raise ProbeSafetyError("AliPOS base URL must not contain credentials")

    deployed_id = str(config["deployed_restaurant_id"])
    dummy_id = str(config["dummy_restaurant_id"])
    if not UUID_RE.fullmatch(deployed_id) or not UUID_RE.fullmatch(dummy_id):
        raise ProbeSafetyError("Restaurant IDs must be UUIDs")
    if deployed_id.casefold() == dummy_id.casefold():
        raise ProbeSafetyError("Dummy restaurant ID matches the deployed restaurant ID")

    order_ids = tuple(config.get("dummy_order_ids", ()))
    if len(order_ids) != 2 or any(not UUID_RE.fullmatch(str(value)) for value in order_ids):
        raise ProbeSafetyError("Exactly two valid dummy order IDs are required")
    if require_live and not bool(config.get("live_enabled")):
        raise LiveProbesDisabled(f"Set {LIVE_FLAG_NAME}=1 only for the approved live run")
```

Add empty, ordered code cells tagged `probe-library` for later redaction, routing, client, and reporting helpers. Add ordered code cells tagged `probe-live` for later configuration, self-check, authentication, baseline, order, discovery, and report orchestration. Do not put executable network code in them yet.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit the safe scaffold**

```bash
git add notebooks/alipos_table_booking_discovery.ipynb tests/notebooks/test_alipos_table_booking_discovery.py
git commit -m "test: scaffold safe AliPOS discovery notebook"
```

---

### Task 2: Recursive redaction, payload summaries, and result classification

**Files:**
- Modify: `notebooks/alipos_table_booking_discovery.ipynb`
- Modify: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Consumes: `UUID_PATTERN` and `UUID_RE` from Task 1.
- Produces: `fingerprint_identifier(value)`, `sanitize_text(text)`, `redact_value(value, key="")`, `summarize_payload(payload, route_name="")`, `extract_hall_table_ids(payload)`, `classify_result(result)`, and `summarize_result(result)`.

- [ ] **Step 1: Add failing redaction and classification tests**

Append these tests:

```python
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
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -k "redaction or halls or classification" -v
```

Expected: FAIL because the redaction and summary functions are undefined.

- [ ] **Step 3: Implement redaction and result summaries in the second library cell**

Put this complete source in the next `probe-library` cell:

```python
import hashlib
from typing import Sequence


SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "authorization",
    "clientsecret",
    "client_secret",
    "clientname",
    "phone",
    "address",
    "latitude",
    "longitude",
    "email",
    "card",
    "pan",
    "otp",
    "paymentinfo",
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
UZ_PHONE_RE = re.compile(r"\+?998[0-9 ()-]{9,16}")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~-]+")
UUID_TEXT_RE = re.compile(UUID_PATTERN)


def fingerprint_identifier(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"id:{digest}"


def sanitize_text(text: str) -> str:
    value = UUID_TEXT_RE.sub(lambda match: fingerprint_identifier(match.group(0)), str(text))
    value = BEARER_RE.sub("Bearer [REDACTED]", value)
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = UZ_PHONE_RE.sub("[REDACTED_PHONE]", value)
    return value[:500]


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(part.replace("_", "") in normalized for part in SENSITIVE_KEY_PARTS)


def redact_value(value: Any, key: str = "") -> Any:
    if key and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        if UUID_RE.fullmatch(value):
            return fingerprint_identifier(value)
        return sanitize_text(value)
    return value


def _case_insensitive_get(mapping: Mapping[str, Any], name: str, default: Any) -> Any:
    wanted = name.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == wanted:
            return value
    return default


def _safe_collection_metadata(items: Sequence[Any]) -> dict:
    item_fields = []
    if items and isinstance(items[0], Mapping):
        item_fields = sorted(str(key) for key in items[0].keys())
    return {"count": len(items), "item_fields": item_fields}


def _safe_hall_table_preview(payload: Mapping[str, Any]) -> dict:
    halls = _case_insensitive_get(payload, "halls", [])
    tables = _case_insensitive_get(payload, "tables", [])
    safe_halls = []
    safe_tables = []
    for hall in halls if isinstance(halls, list) else []:
        if not isinstance(hall, Mapping):
            continue
        safe_halls.append(
            {
                "id": redact_value(_case_insensitive_get(hall, "id", "")),
                "title": sanitize_text(str(_case_insensitive_get(hall, "title", ""))),
                "servicePercent": _case_insensitive_get(hall, "servicePercent", None),
            }
        )
    for table in tables if isinstance(tables, list) else []:
        if not isinstance(table, Mapping):
            continue
        safe_tables.append(
            {
                "id": redact_value(_case_insensitive_get(table, "id", "")),
                "title": sanitize_text(str(_case_insensitive_get(table, "title", ""))),
                "hallId": redact_value(_case_insensitive_get(table, "hallId", "")),
            }
        )
    return {"halls": safe_halls, "tables": safe_tables}


def summarize_payload(payload: Any, route_name: str = "") -> dict:
    if isinstance(payload, Mapping):
        collections = {
            str(key): _safe_collection_metadata(value)
            for key, value in payload.items()
            if isinstance(value, list)
        }
        summary = {
            "type": "object",
            "fields": sorted(str(key) for key in payload.keys()),
            "collections": collections,
        }
        if route_name == "halls_and_tables":
            summary["preview"] = _safe_hall_table_preview(payload)
        return summary
    if isinstance(payload, list):
        return {
            "type": "array",
            "count": len(payload),
            "item_fields": (
                sorted(str(key) for key in payload[0].keys())
                if payload and isinstance(payload[0], Mapping)
                else []
            ),
        }
    if payload is None:
        return {"type": "none"}
    return {"type": type(payload).__name__}


def extract_hall_table_ids(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(payload, Mapping):
        return None, None
    halls = _case_insensitive_get(payload, "halls", [])
    tables = _case_insensitive_get(payload, "tables", [])

    def first_id(items: Any) -> Optional[str]:
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, Mapping):
                continue
            value = _case_insensitive_get(item, "id", "")
            if isinstance(value, str) and UUID_RE.fullmatch(value):
                return value
        return None

    return first_id(halls), first_id(tables)


def classify_result(result: Mapping[str, Any]) -> str:
    status = result.get("status")
    content_type = str(result.get("content_type", "")).casefold()
    allow = {part.strip().upper() for part in str(result.get("allow", "")).split(",") if part.strip()}
    if status in (401, 403):
        return "unauthorized/forbidden"
    if status in (400, 409, 422):
        return "invalid test data"
    if status == 404:
        return "unsupported"
    if status == 405:
        return "ambiguous" if {"GET", "OPTIONS"} & allow else "unsupported"
    if isinstance(status, int) and 200 <= status < 300:
        if "json" in content_type and result.get("payload") is not None:
            return "confirmed"
        return "ambiguous"
    return "ambiguous"


def summarize_result(result: Mapping[str, Any]) -> dict:
    return {
        "name": str(result.get("name", "")),
        "family": str(result.get("family", "")),
        "method": str(result.get("method", "")),
        "path": sanitize_text(str(result.get("path", ""))),
        "status": result.get("status"),
        "classification": classify_result(result),
        "latency_ms": result.get("latency_ms"),
        "content_type": sanitize_text(str(result.get("content_type", ""))),
        "allow": sanitize_text(str(result.get("allow", ""))),
        "shape": summarize_payload(result.get("payload"), str(result.get("name", ""))),
        "error": sanitize_text(str(result.get("error", ""))),
    }
```

- [ ] **Step 4: Run all notebook unit tests**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit redaction and classification**

```bash
git add notebooks/alipos_table_booking_discovery.ipynb tests/notebooks/test_alipos_table_booking_discovery.py
git commit -m "feat: redact AliPOS discovery results"
```

---

### Task 3: Documented routes, booking matrix, and request-budget selection

**Files:**
- Modify: `notebooks/alipos_table_booking_discovery.ipynb`
- Modify: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Consumes: dummy restaurant/order IDs from Task 1 and discovered hall/table IDs from Task 2.
- Produces: `BOOKING_TERMS`, `build_documented_routes(restaurant_id)`, `build_order_routes(order_ids)`, `build_booking_routes(restaurant_id, hall_id=None, table_id=None)`, `select_get_routes(candidates, completed_count)`, and `build_option_routes(get_results, completed_count)`.

- [ ] **Step 1: Add failing route and budget tests**

Append:

```python
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
```

- [ ] **Step 2: Run the route tests and verify they fail**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -k "routes or booking_matrix or selection" -v
```

Expected: FAIL because route builders are undefined.

- [ ] **Step 3: Implement the deterministic route matrix in the third library cell**

Put this source in the next `probe-library` cell:

```python
MAX_TOTAL_REQUESTS = 120
OPTIONS_RESERVE = 12
BOOKING_TERMS = (
    "tableBooking",
    "table-booking",
    "tableReservation",
    "table-reservation",
    "booking",
    "bookings",
    "reservation",
    "reservations",
    "availability",
    "tableAvailability",
    "table-availability",
    "bookingAvailability",
    "booking-availability",
    "table",
    "tables",
    "hall",
    "halls",
    "floor",
    "floors",
    "reserve",
    "reserves",
    "bron",
)
ID_SCOPED_TERMS = BOOKING_TERMS


def _route(name: str, family: str, path: str, method: str = "GET") -> dict:
    return {"name": name, "family": family, "method": method, "path": path}


def _deduplicate_routes(routes: Sequence[Mapping[str, str]]) -> list:
    selected = []
    seen = set()
    for route in routes:
        key = (str(route["method"]), str(route["path"]))
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(route))
    return selected


def build_documented_routes(restaurant_id: str) -> list:
    return [
        _route("restaurants", "documented", "/restaurants"),
        _route("payment_methods", "documented", "/api/Integration/v1/paymentMethod/all"),
        _route(
            "menu_composition",
            "documented",
            f"/api/Integration/v1/menu/{restaurant_id}/composition",
        ),
        _route(
            "halls_and_tables",
            "documented",
            f"/api/Integration/v1/restaurant/{restaurant_id}/halls-and-tables",
        ),
    ]


def build_order_routes(order_ids: Sequence[str]) -> list:
    routes = []
    for index, order_id in enumerate(order_ids, start=1):
        routes.append(
            _route(
                f"dummy_order_{index}",
                "order_read",
                f"/api/Integration/v1/order/{order_id}",
            )
        )
        routes.append(
            _route(
                f"dummy_order_status_{index}",
                "order_read",
                f"/api/Integration/v1/order/{order_id}/status",
            )
        )
    return routes


def build_booking_routes(
    restaurant_id: str,
    hall_id: Optional[str] = None,
    table_id: Optional[str] = None,
) -> list:
    routes = []
    for term in BOOKING_TERMS:
        routes.extend(
            [
                _route(f"{term}_top", "top_level", f"/api/Integration/v1/{term}"),
                _route(
                    f"{term}_restaurant_scoped",
                    "restaurant_scoped",
                    f"/api/Integration/v1/restaurant/{restaurant_id}/{term}",
                ),
                _route(
                    f"{term}_restaurant_argument",
                    "argument",
                    f"/api/Integration/v1/{term}/{restaurant_id}",
                ),
                _route(
                    f"{term}_menu_scoped",
                    "menu_scoped",
                    f"/api/Integration/v1/menu/{restaurant_id}/{term}",
                ),
            ]
        )

    for term in ID_SCOPED_TERMS:
        if table_id:
            routes.extend(
                [
                    _route(
                        f"{term}_table_argument",
                        "id_scoped",
                        f"/api/Integration/v1/{term}/{table_id}",
                    ),
                    _route(
                        f"{term}_restaurant_table",
                        "id_scoped",
                        f"/api/Integration/v1/restaurant/{restaurant_id}/{term}/{table_id}",
                    ),
                ]
            )
        if hall_id:
            routes.extend(
                [
                    _route(
                        f"{term}_hall_argument",
                        "id_scoped",
                        f"/api/Integration/v1/{term}/{hall_id}",
                    ),
                    _route(
                        f"{term}_restaurant_hall",
                        "id_scoped",
                        f"/api/Integration/v1/restaurant/{restaurant_id}/{term}/{hall_id}",
                    ),
                ]
            )
    return _deduplicate_routes(routes)


def select_get_routes(
    candidates: Sequence[Mapping[str, str]],
    completed_count: int,
) -> list:
    available = max(0, MAX_TOTAL_REQUESTS - OPTIONS_RESERVE - completed_count)
    return [dict(route) for route in candidates[:available]]


def build_option_routes(
    get_results: Sequence[Mapping[str, Any]],
    completed_count: int,
) -> list:
    available = max(0, MAX_TOTAL_REQUESTS - completed_count)
    method_failures = [result for result in get_results if result.get("status") == 405]
    representatives = []
    represented_families = set()
    for result in get_results:
        family = str(result.get("family", ""))
        if result.get("status") != 404 or family in represented_families:
            continue
        represented_families.add(family)
        representatives.append(result)

    routes = [
        _route(
            f"options_{result.get('name', 'route')}",
            str(result.get("family", "")),
            str(result.get("path", "")),
            method="OPTIONS",
        )
        for result in (*method_failures, *representatives)
    ]
    return _deduplicate_routes(routes)[:available]
```

- [ ] **Step 4: Run all notebook tests**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the route inventory**

```bash
git add notebooks/alipos_table_booking_discovery.ipynb tests/notebooks/test_alipos_table_booking_discovery.py
git commit -m "feat: build AliPOS booking route matrix"
```

---

### Task 4: Read-only HTTP client with fake-transport tests

**Files:**
- Modify: `notebooks/alipos_table_booking_discovery.ipynb`
- Modify: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Consumes: validated configuration, `classify_result`, and route dictionaries.
- Produces: `UnsafeMethodError`, `UnsafeRedirectError`, `AuthenticationError`, `RequestBudgetExceeded`, `NoRedirectHandler`, `SafeAliPOSClient`, and `run_routes(client, routes)`.

- [ ] **Step 1: Add fake-response, method-blocking, redirect, and no-retry tests**

Append:

```python
from urllib.error import URLError


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
    assert len(opener.requests) == 1
```

- [ ] **Step 2: Run the HTTP-client tests and verify they fail**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -k "client" -v
```

Expected: FAIL because `SafeAliPOSClient` is undefined.

- [ ] **Step 3: Implement the HTTP client in the fourth library cell**

Put this source in the next `probe-library` cell:

```python
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener
import time


ALLOWED_DISCOVERY_METHODS = frozenset({"GET", "OPTIONS"})
MAX_RESPONSE_BYTES = 5_000_000


class UnsafeMethodError(ProbeSafetyError):
    pass


class UnsafeRedirectError(ProbeSafetyError):
    pass


class AuthenticationError(ProbeSafetyError):
    pass


class RequestBudgetExceeded(ProbeSafetyError):
    pass


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise UnsafeRedirectError("Redirects are disabled for AliPOS discovery")


def _header_value(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    value = headers.get(name, "")
    return str(value or "")


def _read_limited_body(response: Any) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    return body[:MAX_RESPONSE_BYTES]


def _decode_payload(body: bytes, content_type: str) -> Tuple[Any, str]:
    if not body:
        return None, ""
    text = body.decode("utf-8", errors="replace")
    if "json" in content_type.casefold() or text.lstrip().startswith(("{", "[")):
        try:
            return json.loads(text), ""
        except ValueError:
            return None, "Malformed JSON response"
    return None, "Non-JSON response body suppressed"


class SafeAliPOSClient:
    def __init__(
        self,
        config: Mapping[str, Any],
        opener: Any = None,
        sleep_fn: Any = time.sleep,
        monotonic_fn: Any = time.monotonic,
    ) -> None:
        validate_probe_config(config, require_live=True)
        self._config = dict(config)
        self._origin = urlsplit(str(config["base_url"]))
        self._opener = opener or build_opener(NoRedirectHandler())
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._access_token = None
        self._request_count = 0
        self._rate_limited = False
        self._last_request_at = None

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def rate_limited(self) -> bool:
        return self._rate_limited

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ProbeSafetyError("Probe path must start with a slash")
        url = urljoin(f"{self._config['base_url']}/", path.lstrip("/"))
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != (self._origin.scheme, self._origin.netloc):
            raise UnsafeRedirectError("Probe URL origin differs from AliPOS origin")
        return url

    def _assert_final_origin(self, response: Any) -> None:
        final_url = str(response.geturl())
        parsed = urlsplit(final_url)
        if (parsed.scheme, parsed.netloc) != (self._origin.scheme, self._origin.netloc):
            raise UnsafeRedirectError("Response URL origin differs from AliPOS origin")

    def _throttle(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = float(self._config["minimum_interval_seconds"]) - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def authenticate(self) -> None:
        body = urlencode(
            {
                "client_id": self._config["client_id"],
                "client_secret": self._config["client_secret"],
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = Request(
            self._build_url("/security/oauth/token"),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._opener.open(
                request,
                timeout=int(self._config["timeout_seconds"]),
            ) as response:
                self._assert_final_origin(response)
                status = int(getattr(response, "status", 200))
                payload = json.loads(_read_limited_body(response).decode("utf-8"))
        except HTTPError as exc:
            raise AuthenticationError(f"AliPOS authentication returned HTTP {exc.code}") from exc
        except (URLError, ValueError, KeyError) as exc:
            raise AuthenticationError("AliPOS authentication did not return a usable token") from exc
        if not 200 <= status < 300:
            raise AuthenticationError(f"AliPOS authentication returned HTTP {status}")
        token = payload.get("access_token") if isinstance(payload, Mapping) else None
        if not isinstance(token, str) or not token:
            raise AuthenticationError("AliPOS authentication response omitted access_token")
        self._access_token = token

    def request(self, method: str, path: str, name: str, family: str) -> dict:
        normalized_method = method.upper()
        if normalized_method not in ALLOWED_DISCOVERY_METHODS:
            raise UnsafeMethodError(f"HTTP method {normalized_method} is blocked")
        if not self._access_token:
            raise AuthenticationError("Authenticate before running discovery requests")
        if self._rate_limited:
            raise RequestBudgetExceeded("AliPOS discovery stopped after rate limit")
        if self._request_count >= int(self._config["max_requests"]):
            raise RequestBudgetExceeded("AliPOS discovery request budget is exhausted")

        url = self._build_url(path)
        self._throttle()
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
            },
            method=normalized_method,
        )
        self._request_count += 1
        started_at = self._monotonic()
        status = None
        headers = {}
        payload = None
        error = ""
        try:
            with self._opener.open(
                request,
                timeout=int(self._config["timeout_seconds"]),
            ) as response:
                self._assert_final_origin(response)
                status = int(getattr(response, "status", 200))
                headers = response.headers
                content_type = _header_value(headers, "Content-Type")
                payload, error = _decode_payload(_read_limited_body(response), content_type)
        except HTTPError as exc:
            status = int(exc.code)
            headers = exc.headers
            content_type = _header_value(headers, "Content-Type")
            payload, error = _decode_payload(_read_limited_body(exc), content_type)
        except URLError as exc:
            content_type = ""
            error = sanitize_text(str(exc.reason))

        result = {
            "name": name,
            "family": family,
            "method": normalized_method,
            "path": path,
            "status": status,
            "latency_ms": round((self._monotonic() - started_at) * 1000, 1),
            "content_type": content_type,
            "allow": _header_value(headers, "Allow"),
            "payload": payload,
            "error": error,
        }
        result["classification"] = classify_result(result)
        if status == 429:
            self._rate_limited = True
        return result


def run_routes(client: SafeAliPOSClient, routes: Sequence[Mapping[str, str]]) -> list:
    results = []
    for route in routes:
        try:
            result = client.request(
                str(route["method"]),
                str(route["path"]),
                str(route["name"]),
                str(route["family"]),
            )
        except RequestBudgetExceeded:
            break
        results.append(result)
        if result.get("status") == 429:
            break
    return results
```

- [ ] **Step 4: Run all notebook tests**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS, and the no-retry test records exactly one transport call.

- [ ] **Step 5: Commit the read-only client**

```bash
git add notebooks/alipos_table_booking_discovery.ipynb tests/notebooks/test_alipos_table_booking_discovery.py
git commit -m "feat: add read-only AliPOS probe client"
```

---

### Task 5: Notebook orchestration, dry-run report, and static mutation audit

**Files:**
- Modify: `notebooks/alipos_table_booking_discovery.ipynb`
- Modify: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Consumes: all helpers and route builders from Tasks 1-4.
- Produces: ordered `probe-live` cells, `render_markdown_report(results, dry_routes=())`, `REPORT`, and sanitized saved output.

**Approved authorization amendment (2026-07-10):** The saved restaurant ID is
the deployed restaurant ID. Before the existing Task 5 steps, add a failing
regression proving that equality is harmless in dry mode but live construction
requires the second explicit flag. Then add
`DEPLOYED_LIVE_FLAG_NAME = "ALLOW_DEPLOYED_ALIPOS_READS"`, include
`deployed_reads_enabled` in `build_probe_config`, and change the equality guard
to:

```python
target_is_deployed = deployed_id.casefold() == dummy_id.casefold()
if target_is_deployed and require_live and not bool(config.get("deployed_reads_enabled")):
    raise ProbeSafetyError("Deployed restaurant reads require explicit authorization")
```

Use this regression test:

```python
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
```

- [ ] **Step 1: Add failing report-redaction and live-cell method tests**

Append:

```python
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
```

Also add `import re` near the top of the test file.

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -k "rendered_report or live_cells" -v
```

Expected: FAIL because `render_markdown_report` and live orchestration are incomplete.

- [ ] **Step 3: Implement Markdown reporting in the fifth library cell**

Put this source in the last `probe-library` cell:

```python
from collections import Counter


def render_markdown_report(
    results: Sequence[Mapping[str, Any]],
    dry_routes: Sequence[Mapping[str, str]] = (),
) -> str:
    lines = ["# AliPOS Table Booking Discovery", ""]
    if dry_routes and not results:
        lines.extend(
            [
                "**Mode:** dry run; no AliPOS API request was sent.",
                "",
                f"Planned GET routes: {len(dry_routes)}",
                "",
                "Live execution requires both explicit AliPOS read flags.",
            ]
        )
        return "\n".join(lines)

    summaries = [summarize_result(result) for result in results]
    counts = Counter(summary["classification"] for summary in summaries)
    lines.extend(["**Mode:** live read-only probe.", "", "## Classification counts", ""])
    for name in (
        "confirmed",
        "unsupported",
        "unauthorized/forbidden",
        "invalid test data",
        "ambiguous",
        "skipped",
    ):
        lines.append(f"- {name}: {counts.get(name, 0)}")

    lines.extend(["", "## Route results", ""])
    lines.append("| Method | Route | Status | Classification | Shape |")
    lines.append("|---|---|---:|---|---|")
    for summary in summaries:
        shape = json.dumps(summary["shape"], ensure_ascii=False, sort_keys=True)
        lines.append(
            "| {method} | `{path}` | {status} | {classification} | `{shape}` |".format(
                method=summary["method"],
                path=summary["path"].replace("|", "\\|"),
                status=summary["status"] if summary["status"] is not None else "network-error",
                classification=summary["classification"],
                shape=shape.replace("|", "\\|")[:500],
            )
        )

    confirmed_booking = [
        summary
        for summary in summaries
        if summary["classification"] == "confirmed"
        and summary["method"] == "GET"
        and summary["family"] not in {"documented", "order_read"}
    ]
    lines.extend(["", "## Conclusion", ""])
    if confirmed_booking:
        lines.append("At least one non-documented booking-related read route returned usable JSON.")
    else:
        lines.append("No native booking or availability read route was confirmed by this run.")
    lines.append("A successful halls-and-tables route confirms table discovery, not reservation support.")
    return "\n".join(lines)
```

- [ ] **Step 4: Fill the ordered live cells without displaying raw objects**

Use these exact cell responsibilities and sources.

Configuration cell (`probe-live`):

```python
ROOT = find_repo_root()
CONFIG = build_probe_config(ROOT)
validate_probe_config(CONFIG, require_live=False)
print("Configuration loaded; deployed target requires the second live-read flag.")
print("Live reads enabled:", CONFIG["live_enabled"])
print("Deployed reads enabled:", CONFIG["deployed_reads_enabled"])
```

Synthetic self-check cell (`probe-live`):

```python
_synthetic_config = dict(CONFIG)
_synthetic_config.update(
    {
        "base_url": "https://web.alipos.uz",
        "client_id": "synthetic-client-id",
        "client_secret": "synthetic-client-secret",
        "deployed_restaurant_id": "22222222-2222-4222-8222-222222222222",
        "dummy_restaurant_id": "11111111-1111-4111-8111-111111111111",
        "dummy_order_ids": (
            "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444",
        ),
        "live_enabled": True,
    }
)
validate_probe_config(_synthetic_config)
assert redact_value({"phoneNumber": "+998901234567"})["phoneNumber"] == "[REDACTED]"
assert all(route["method"] == "GET" for route in build_documented_routes(_synthetic_config["dummy_restaurant_id"]))
print("Offline safety self-checks passed.")
```

Authentication and route setup cell (`probe-live`):

```python
CLIENT = None
RESULTS = []
DOCUMENTED_ROUTES = build_documented_routes(CONFIG["dummy_restaurant_id"])
ORDER_ROUTES = build_order_routes(CONFIG["dummy_order_ids"])
if CONFIG["live_enabled"]:
    validate_probe_config(CONFIG, require_live=True)
    CLIENT = SafeAliPOSClient(CONFIG)
    CLIENT.authenticate()
    print("AliPOS authentication succeeded; token output is suppressed.")
else:
    print("Dry run: authentication and all network requests are skipped.")
```

Documented baseline and dummy order cell (`probe-live`):

```python
HALL_ID = None
TABLE_ID = None
if CLIENT is not None:
    baseline_results = run_routes(CLIENT, DOCUMENTED_ROUTES)
    RESULTS.extend(baseline_results)
    halls_result = next(
        (result for result in baseline_results if result["name"] == "halls_and_tables"),
        None,
    )
    if halls_result is not None:
        HALL_ID, TABLE_ID = extract_hall_table_ids(halls_result.get("payload"))
    RESULTS.extend(run_routes(CLIENT, ORDER_ROUTES))
    print("Documented and dummy-order GET probes completed.")
else:
    print("Dry run documented route names:", [route["name"] for route in DOCUMENTED_ROUTES])
    print("Dry run dummy-order route count:", len(ORDER_ROUTES))
```

Booking discovery and `OPTIONS` cell (`probe-live`):

```python
BOOKING_CANDIDATES = build_booking_routes(
    CONFIG["dummy_restaurant_id"],
    hall_id=HALL_ID,
    table_id=TABLE_ID,
)
if CLIENT is not None:
    selected_gets = select_get_routes(BOOKING_CANDIDATES, CLIENT.request_count)
    booking_results = run_routes(CLIENT, selected_gets)
    RESULTS.extend(booking_results)
    option_routes = build_option_routes(booking_results, CLIENT.request_count)
    RESULTS.extend(run_routes(CLIENT, option_routes))
    print("Booking discovery completed within request budget:", CLIENT.request_count)
else:
    selected_gets = select_get_routes(
        BOOKING_CANDIDATES,
        len(DOCUMENTED_ROUTES) + len(ORDER_ROUTES),
    )
    print("Dry run booking GET route count:", len(selected_gets))
```

Final report cell (`probe-live`):

```python
from IPython.display import Markdown, display


DRY_ROUTES = [] if CLIENT is not None else [*DOCUMENTED_ROUTES, *ORDER_ROUTES, *selected_gets]
REPORT = render_markdown_report(RESULTS, dry_routes=DRY_ROUTES)
display(Markdown(REPORT))
```

Ensure no cell ends with `CONFIG`, `CLIENT`, `RESULTS`, a raw payload, or an access-token variable.

- [ ] **Step 5: Run unit tests and execute a dry notebook run**

Run tests:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS.

Run the notebook with live reads explicitly disabled:

```bash
ALLOW_LIVE_ALIPOS_READS=0 ALLOW_DEPLOYED_ALIPOS_READS=0 uv run --with nbconvert --with ipykernel jupyter nbconvert --to notebook --execute --inplace notebooks/alipos_table_booking_discovery.ipynb --ExecutePreprocessor.timeout=600 --ExecutePreprocessor.kernel_name=python3
```

Expected: execution succeeds, output says `Dry run`, and no AliPOS authentication request is made.

- [ ] **Step 6: Commit orchestration and the dry-run output**

```bash
git add notebooks/alipos_table_booking_discovery.ipynb tests/notebooks/test_alipos_table_booking_discovery.py
git commit -m "feat: orchestrate AliPOS booking discovery notebook"
```

---

### Task 6: Live read-only execution, output audit, and final evidence

**Files:**
- Modify: `notebooks/alipos_table_booking_discovery.ipynb` (execution counts and sanitized outputs only)
- Test: `tests/notebooks/test_alipos_table_booking_discovery.py`

**Interfaces:**
- Consumes: complete notebook and official `.env` credentials.
- Produces: one fully executed notebook with sanitized classifications and a Markdown conclusion.

- [ ] **Step 1: Run the complete offline suite immediately before network access**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS. Do not continue to the live run if any test fails.

- [ ] **Step 2: Execute the notebook once with the approved live flag**

Run:

```bash
ALLOW_LIVE_ALIPOS_READS=1 ALLOW_DEPLOYED_ALIPOS_READS=1 uv run --with nbconvert --with ipykernel jupyter nbconvert --to notebook --execute --inplace notebooks/alipos_table_booking_discovery.ipynb --ExecutePreprocessor.timeout=900 --ExecutePreprocessor.kernel_name=python3
```

Expected: execution exits 0, authentication reports success without a token, the request count is at most 120, and the final Markdown report contains route classifications. If authentication fails, stop and diagnose without printing `.env` values; do not treat the task as complete.

- [ ] **Step 3: Audit saved outputs for secrets, raw identifiers, PII, and error traces**

Run this read-only audit:

```bash
/usr/bin/python3 - <<'PY'
import json
import re
from pathlib import Path

root = Path.cwd()
notebook = json.loads((root / "notebooks/alipos_table_booking_discovery.ipynb").read_text())
dotenv = {}
for raw in (root / ".env").read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    dotenv[key.strip()] = value.strip().strip("\"'")

parts = []
error_outputs = []
for cell in notebook.get("cells", []):
    for output in cell.get("outputs", []):
        if output.get("output_type") == "error":
            error_outputs.append(output.get("ename", "error"))
        text = output.get("text", "")
        if isinstance(text, list):
            parts.extend(str(item) for item in text)
        elif text:
            parts.append(str(text))
        for value in output.get("data", {}).values():
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif isinstance(value, str):
                parts.append(value)
outputs = "\n".join(parts)

for key in ("ALIPOS_API_CLIENT_ID", "ALIPOS_API_CLIENT_SECRET"):
    value = dotenv.get(key, "")
    if value and value in outputs:
        raise SystemExit(f"secret leak detected for {key}")
if re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", outputs):
    raise SystemExit("raw UUID detected in notebook output")
if re.search(r"\+?998[0-9 ()-]{9,16}", outputs):
    raise SystemExit("phone number detected in notebook output")
if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", outputs):
    raise SystemExit("email address detected in notebook output")
if re.search(r"(?i)\bBearer\s+[A-Za-z0-9._~-]+", outputs):
    raise SystemExit("bearer token detected in notebook output")
if error_outputs:
    raise SystemExit(f"notebook contains error outputs: {error_outputs}")
if "# AliPOS Table Booking Discovery" not in outputs:
    raise SystemExit("final discovery report is missing")
print("Notebook output audit passed")
PY
```

Expected: `Notebook output audit passed`.

- [ ] **Step 4: Inspect the sanitized report and verify the safety invariants**

Run:

```bash
jq -r '.cells[] | .outputs[]? | .data["text/markdown"]? // empty | if type == "array" then join("") else . end' notebooks/alipos_table_booking_discovery.ipynb
```

Expected: a report listing documented and speculative route results with masked paths, statuses, shapes, and a conclusion. Confirm manually that:

- `halls_and_tables` is present;
- total live post-authentication calls do not exceed 120;
- only `GET` and `OPTIONS` appear in route rows;
- the deployed restaurant UUID does not appear;
- no raw response body or personal data appears;
- the conclusion distinguishes table discovery from native reservation support.

- [ ] **Step 5: Re-run tests after the executed notebook is saved**

Run:

```bash
/usr/bin/python3 -m pytest tests/notebooks/test_alipos_table_booking_discovery.py -v
```

Expected: all tests PASS against the executed notebook.

- [ ] **Step 6: Review the exact diff and commit only the executed notebook**

Run:

```bash
git status --short
git diff --check
git diff -- notebooks/alipos_table_booking_discovery.ipynb
```

Confirm that existing untracked notebooks and AliPOS documents remain untouched. Then commit:

```bash
git add notebooks/alipos_table_booking_discovery.ipynb
git commit -m "chore: record AliPOS booking discovery run"
```

- [ ] **Step 7: Prepare the user-facing findings**

Report only the sanitized facts shown by the executed notebook:

- whether authentication and `halls-and-tables` worked;
- hall/table response fields and counts without raw IDs;
- any confirmed booking/availability read routes;
- representative unsupported or method-restricted route families;
- ambiguous results and the exact questions still needed for AliPOS support;
- links to the notebook and approved design/plan files.
