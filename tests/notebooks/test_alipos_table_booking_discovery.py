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
