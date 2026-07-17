import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_table_qr_assets.py"
SPEC = importlib.util.spec_from_file_location("generate_table_qr_assets", SCRIPT)
assert SPEC and SPEC.loader
qr_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr_assets)


def manifest():
    return {
        "success": True,
        "data": [
            {
                "table_title": "Stol 2",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": "2",
                "start_param": "t2_2_abcdefghijkl",
                "deep_link": "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_abcdefghijkl",
            },
            {
                "table_title": "Stol 12",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": "12",
                "start_param": "t2_12_mnopqrstuvwx",
                "deep_link": "https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_mnopqrstuvwx",
            },
        ],
    }


def test_generate_package_renders_decodable_sorted_assets(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(manifest()), encoding="utf-8")
    output = tmp_path / "table-qr-codes"

    rows = qr_assets.load_manifest(source)
    zip_path = qr_assets.generate_package(rows, output)

    pngs = sorted((output / "png").glob("*.png"))
    assert [path.name[:6] for path in pngs] == ["000002", "000012"]
    decoded = [zxingcpp.read_barcode(Image.open(path)).text for path in pngs]
    assert decoded == [row["deep_link"] for row in rows]
    assert (output / "all-table-qr-codes.pdf").stat().st_size > 0
    assert json.loads((output / "verification.json").read_text())["verified_count"] == 2
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "manifest.csv" in names
    assert "all-table-qr-codes.pdf" in names
    assert len([name for name in names if name.startswith("png/")]) == 2


def test_manifest_rejects_duplicate_or_mismatched_codes(tmp_path):
    payload = manifest()
    payload["data"][1]["manual_code"] = "2"
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate manual code"):
        qr_assets.load_manifest(source)


def test_api_verification_compares_only_safe_table_fields(monkeypatch):
    row = manifest()["data"][0]
    response = {
        "success": True,
        "data": {
            "table_title": row["table_title"],
            "hall_title": row["hall_title"],
            "manual_code": row["manual_code"],
            "access_token": "must-not-be-written-to-artifacts",
        },
    }
    monkeypatch.setattr(
        qr_assets.urllib.request,
        "urlopen",
        lambda request, timeout: io.StringIO(json.dumps(response)),
    )

    qr_assets.verify_api([row], "https://restaurant.labtutor.app/api")
