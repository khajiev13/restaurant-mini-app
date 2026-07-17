import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image, ImageChops
from pypdf import PdfReader

SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_table_qr_assets.py"
README = Path(__file__).parents[2] / "README.md"
SPEC = importlib.util.spec_from_file_location("generate_table_qr_assets", SCRIPT)
assert SPEC and SPEC.loader
qr_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr_assets)

TOKEN_SENTINEL = "must-not-be-written-to-artifacts"


def _row(
    code: str,
    signature: str,
    *,
    hall_title: str = "Asosiy zal",
    table_title: str | None = None,
    service_percent: int | float = 10,
) -> dict:
    start_param = f"t2_{code}_{signature}"
    return {
        "table_title": table_title or f"Stol {code}",
        "hall_title": hall_title,
        "service_percent": service_percent,
        "manual_code": code,
        "start_param": start_param,
        "deep_link": (f"https://t.me/olotsomsa_zakaz_bot?startapp={start_param}"),
    }


def manifest_rows() -> list[dict]:
    return [
        _row("2", "AbCdEf012_-x"),
        _row("12", "mnOPqr345_-z"),
    ]


def manifest() -> dict:
    return {"success": True, "data": manifest_rows()}


def _write_manifest(tmp_path: Path, payload) -> Path:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


def _resolver_payload(row: dict) -> dict:
    return {
        "success": True,
        "data": {
            "table_title": row["table_title"],
            "hall_title": row["hall_title"],
            "service_percent": row["service_percent"],
            "manual_code": row["manual_code"],
            "access_token": TOKEN_SENTINEL,
        },
    }


@pytest.fixture(scope="module")
def generated_package(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("qr-assets")
    rows = [
        *manifest_rows(),
        _row(
            "3",
            "000000000003",
            hall_title="O'zbekiston milliy taomlari va mehmonlar uchun katta zal",
            table_title="Очень длинное название стола для семейных гостей 3",
        ),
        _row("4", "000000000004"),
        _row("5", "000000000005"),
    ]
    rows[0]["access_token"] = TOKEN_SENTINEL
    source = _write_manifest(tmp_path, {"success": True, "data": rows})
    output = tmp_path / "table-qr-codes.v1"
    safe_rows = qr_assets.load_manifest(source)
    zip_path = qr_assets.generate_package(safe_rows, output)
    return safe_rows, output, zip_path


def test_generate_package_renders_decodable_sorted_assets(generated_package):
    rows, output, _ = generated_package
    pngs = sorted((output / "png").glob("*.png"))

    assert [path.name[:6] for path in pngs] == [
        "000002",
        "000003",
        "000004",
        "000005",
        "000012",
    ]
    expected_by_code = {int(row["manual_code"]): row["deep_link"] for row in rows}
    for path in pngs:
        code = int(path.name.split("-", 1)[0])
        assert zxingcpp.read_barcode(Image.open(path)).text == expected_by_code[code]
    assert json.loads((output / "verification.json").read_text()) == {
        "verified_count": 5
    }


def test_generate_package_paginates_four_cards_per_a4_page(generated_package):
    _, output, _ = generated_package

    pdf = PdfReader(output / "all-table-qr-codes.pdf")

    assert len(pdf.pages) == 2
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(595.2, abs=0.1)
    assert float(pdf.pages[0].mediabox.height) == pytest.approx(841.92, abs=0.1)


def test_generate_package_fits_long_latin_cyrillic_and_uzbek_titles(
    generated_package,
):
    _, output, _ = generated_package
    card_path = next((output / "png").glob("000003-*.png"))
    card = Image.open(card_path).convert("RGB")
    white = Image.new("RGB", (40, 200), "white")

    assert ImageChops.difference(card.crop((0, 130, 40, 330)), white).getbbox() is None
    assert (
        ImageChops.difference(card.crop((1160, 130, 1200, 330)), white).getbbox()
        is None
    )
    title_area = card.crop((40, 130, 1160, 330))
    assert ImageChops.difference(
        title_area, Image.new("RGB", title_area.size, "white")
    ).getbbox()


def test_generate_package_uses_appended_zip_suffix_and_exact_safe_membership(
    generated_package,
):
    rows, output, zip_path = generated_package
    png_names = {
        "png/"
        f"{int(row['manual_code']):06d}-"
        f"{qr_assets._slug(row['hall_title'])}-"
        f"{qr_assets._slug(row['table_title'])}.png"
        for row in rows
    }
    expected_names = {
        "manifest.json",
        "manifest.csv",
        "verification.json",
        "all-table-qr-codes.pdf",
        *png_names,
    }

    assert zip_path == Path(f"{output}.zip")
    with zipfile.ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == expected_names
        assert all(
            TOKEN_SENTINEL.encode() not in archive.read(name)
            for name in archive.namelist()
        )
    assert all("access_token" not in row for row in rows)


def test_manifest_accepts_raw_array_and_mixed_case_urlsafe_signature(tmp_path):
    rows = qr_assets.load_manifest(_write_manifest(tmp_path, manifest_rows()))

    assert [row["manual_code"] for row in rows] == ["2", "12"]
    assert rows[0]["start_param"] == "t2_2_AbCdEf012_-x"


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "data": manifest_rows()},
        {"success": 1, "data": manifest_rows()},
        {"data": manifest_rows()},
        {"success": True, "data": {}},
    ],
)
def test_manifest_rejects_failed_or_malformed_wrappers(tmp_path, payload):
    with pytest.raises(ValueError, match="Manifest envelope"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


def test_manifest_rejects_duplicate_codes(tmp_path):
    payload = manifest()
    payload["data"][1]["manual_code"] = "2"

    with pytest.raises(ValueError, match="Duplicate manual code"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    "service_percent",
    [
        None,
        True,
        "10",
        -0.01,
        100.01,
        10**1000,
        float("nan"),
        float("inf"),
    ],
)
def test_manifest_rejects_missing_wrong_or_out_of_range_service_percent(
    tmp_path, service_percent
):
    payload = manifest()
    payload["data"][0]["service_percent"] = service_percent

    with pytest.raises(ValueError, match="service_percent"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("table_title", None),
        ("hall_title", 123),
        ("manual_code", 2),
        ("start_param", None),
        ("deep_link", []),
    ],
)
def test_manifest_rejects_missing_or_wrong_text_fields(tmp_path, field, value):
    payload = manifest()
    payload["data"][0][field] = value

    with pytest.raises(ValueError, match="missing text fields"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    "start_param",
    [
        "t2_2_abcdefghijk",
        "t2_2_abcdefghijklm",
        "t2_2_abcdefghijk.",
        "t2_02_abcdefghijkl",
        "t2_3_abcdefghijkl",
        "t2_2_abcdefghijkl ",
    ],
)
def test_manifest_rejects_malformed_or_mismatched_start_parameters(
    tmp_path, start_param
):
    payload = manifest()
    payload["data"][0]["start_param"] = start_param
    payload["data"][0]["deep_link"] = (
        f"https://t.me/olotsomsa_zakaz_bot?startapp={start_param}"
    )

    with pytest.raises(ValueError, match="start parameter"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    "deep_link",
    [
        "http://t.me/olotsomsa_zakaz_bot?startapp=t2_2_AbCdEf012_-x",
        "https://example.com/olotsomsa_zakaz_bot?startapp=t2_2_AbCdEf012_-x",
        "https://t.me/?startapp=t2_2_AbCdEf012_-x",
        "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_AbCdEf012_-x&extra=1",
        "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_AbCdEf012_-x#fragment",
        "https://t.me/olotsomsa_zakaz_bot/?startapp=t2_2_AbCdEf012_-x",
        "https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_mnOPqr345_-z",
    ],
)
def test_manifest_rejects_malformed_or_mismatched_deep_links(tmp_path, deep_link):
    payload = manifest()
    payload["data"][0]["deep_link"] = deep_link

    with pytest.raises(ValueError, match="Deep link"):
        qr_assets.load_manifest(_write_manifest(tmp_path, payload))


def test_api_verification_resolves_signed_entry_and_numeric_fallback_safely(
    monkeypatch, capsys
):
    row = manifest_rows()[0]
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        assert timeout == 20
        return io.StringIO(json.dumps(_resolver_payload(row)))

    monkeypatch.setattr(qr_assets.urllib.request, "urlopen", urlopen)

    qr_assets.verify_api([row], "https://restaurant.labtutor.app/api")

    assert [json.loads(request.data) for request in requests] == [
        {"entry": row["start_param"]},
        {"code": row["manual_code"]},
    ]
    assert all(
        request.full_url == "https://restaurant.labtutor.app/api/tables/resolve"
        for request in requests
    )
    assert all(request.method == "POST" for request in requests)
    assert all(
        request.get_header("Content-type") == "application/json" for request in requests
    )
    assert all(request.get_header("Authorization") is None for request in requests)
    assert TOKEN_SENTINEL not in capsys.readouterr().out


@pytest.mark.parametrize("bad_response_index", [0, 1])
@pytest.mark.parametrize(
    "bad_payload",
    [
        {"success": False, "data": {}},
        {"success": 1, "data": {}},
        {"data": {}},
        {"success": True, "data": []},
        {"success": True, "data": {"table_title": "Stol 2"}},
        {
            "success": True,
            "data": {
                "table_title": "Stol 2",
                "hall_title": "Asosiy zal",
                "service_percent": "10",
                "manual_code": "2",
                "access_token": TOKEN_SENTINEL,
            },
        },
        {
            "success": True,
            "data": {
                "table_title": "Stol 2",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": 2,
                "access_token": TOKEN_SENTINEL,
            },
        },
        {
            "success": True,
            "data": {
                "table_title": "Stol 2",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": "2",
            },
        },
    ],
)
def test_api_verification_rejects_failed_or_malformed_responses(
    monkeypatch, bad_response_index, bad_payload
):
    row = manifest_rows()[0]
    payloads = [_resolver_payload(row), _resolver_payload(row)]
    payloads[bad_response_index] = bad_payload

    monkeypatch.setattr(
        qr_assets.urllib.request,
        "urlopen",
        lambda request, timeout: io.StringIO(json.dumps(payloads.pop(0))),
    )

    with pytest.raises(ValueError, match="resolver response"):
        qr_assets.verify_api([row], "https://restaurant.labtutor.app/api")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("table_title", "Other table"),
        ("hall_title", "Other hall"),
        ("service_percent", 11),
        ("manual_code", "3"),
    ],
)
def test_api_verification_rejects_safe_field_mismatches(monkeypatch, field, value):
    row = manifest_rows()[0]
    payload = _resolver_payload(row)
    payload["data"][field] = value

    monkeypatch.setattr(
        qr_assets.urllib.request,
        "urlopen",
        lambda request, timeout: io.StringIO(json.dumps(payload)),
    )

    with pytest.raises(ValueError, match="resolver mismatch"):
        qr_assets.verify_api([row], "https://restaurant.labtutor.app/api")


def test_readme_keeps_admin_jwt_out_of_curl_argv_and_documents_cleanup():
    qr_section = (
        README.read_text(encoding="utf-8")
        .split("## QR Table Ordering", 1)[1]
        .split("Payment behavior:", 1)[0]
    )

    assert "curl --config -" in qr_section
    assert 'curl -fsS -H "Authorization: Bearer $ADMIN_JWT"' not in qr_section
    assert "unset ADMIN_JWT" in qr_section
    assert "umask 077" in qr_section
    assert "rm -f /private/tmp/olot-table-manifest.json" in qr_section
    assert "rm -rf /private/tmp/olot-table-qr-codes" in qr_section
