import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import zxingcpp
from PIL import Image

SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_table_qr_pngs.py"
SPEC = importlib.util.spec_from_file_location("generate_table_qr_pngs", SCRIPT)
assert SPEC and SPEC.loader
qr_pngs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr_pngs)


def manifest_rows():
    rows = []
    for code, signature in (
        ("1", "aaaaaaaaaaaa"),
        ("8", "bbbbbbbbbbbb"),
        ("10", "cccccccccccc"),
        ("30", "dddddddddddd"),
    ):
        start_param = f"t2_{code}_{signature}"
        rows.append(
            {
                "table_title": f"Stoll {code}",
                "hall_title": "Zal",
                "manual_code": code,
                "start_param": start_param,
                "deep_link": (
                    "https://t.me/olotsomsa_zakaz_bot?startapp=" + start_param
                ),
            }
        )
    return rows


def test_gap_manifest_generates_only_raw_verified_pngs(tmp_path):
    output = tmp_path / "table-qr-pngs"
    rows = qr_pngs.validate_manifest_rows(manifest_rows())
    result = qr_pngs.generate_verified_png_folder(rows, output)

    assert result == output
    assert [path.name for path in sorted(output.iterdir())] == [
        "table-01.png",
        "table-08.png",
        "table-10.png",
        "table-30.png",
    ]
    assert not (output / "table-09.png").exists()
    for row, path in zip(rows, sorted(output.iterdir()), strict=True):
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.width == image.height
            assert image.width >= 1200
            assert image.getpixel((0, 0)) == (255, 255, 255)
            assert "transparency" not in image.info
            colors = image.getcolors(maxcolors=3)
            assert colors is not None
            assert {color for _, color in colors} <= {
                (0, 0, 0),
                (255, 255, 255),
            }
            decoded = zxingcpp.read_barcode(image)
        assert decoded is not None
        assert decoded.text == row["deep_link"]

    assert qr_pngs.QUIET_ZONE_MODULES >= 4


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[0].pop("manual_code"),
        lambda rows: rows[0].__setitem__("manual_code", "A1"),
        lambda rows: rows[0].__setitem__("manual_code", "01"),
        lambda rows: rows[1].__setitem__("manual_code", "1"),
        lambda rows: rows[0].__setitem__("table_title", "Stoll 2"),
        lambda rows: rows[0].__setitem__("start_param", "t_AAAAAA_aaaaaaaaaaaa"),
        lambda rows: rows[0].__setitem__("start_param", "t2_2_aaaaaaaaaaaa"),
        lambda rows: rows[0].__setitem__(
            "deep_link",
            "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_aaaaaaaaaaaa",
        ),
    ],
)
def test_manifest_rejects_missing_duplicate_or_mismatched_codes(mutate):
    rows = manifest_rows()
    mutate(rows)
    with pytest.raises(ValueError):
        qr_pngs.validate_manifest_rows(rows)


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def test_deployment_verification_uses_signed_entries_and_safe_fields(monkeypatch):
    rows = qr_pngs.validate_manifest_rows(manifest_rows())
    requests = []

    def fake_urlopen(request, timeout):
        assert timeout == 20
        requests.append(request)
        if request.full_url.endswith(("/healthz", "/api/health")):
            return FakeResponse(b"ok")
        submitted = json.loads(request.data)
        assert set(submitted) == {"entry"}
        row = next(item for item in rows if item["start_param"] == submitted["entry"])
        return FakeResponse(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "manual_code": row["manual_code"],
                        "table_title": row["table_title"],
                        "hall_title": "ignored safe field",
                        "access_token": "must-not-be-persisted-or-printed",
                    },
                }
            ).encode()
        )

    monkeypatch.setattr(qr_pngs.urllib.request, "urlopen", fake_urlopen)
    qr_pngs.verify_deployment(rows, "https://restaurant.labtutor.app")
    resolver_requests = [request for request in requests if request.data is not None]
    assert [json.loads(request.data) for request in resolver_requests] == [
        {"entry": row["start_param"]} for row in rows
    ]


def test_decode_failure_leaves_no_delivery_folder(tmp_path, monkeypatch):
    output = tmp_path / "table-qr-pngs"
    monkeypatch.setattr(
        qr_pngs.zxingcpp,
        "read_barcode",
        lambda image: SimpleNamespace(text="wrong destination"),
    )
    with pytest.raises(ValueError, match="QR decode mismatch"):
        qr_pngs.generate_verified_png_folder(
            qr_pngs.validate_manifest_rows(manifest_rows()),
            output,
        )
    assert not output.exists()


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "table-qr-pngs"
    output.mkdir()
    with pytest.raises(FileExistsError):
        qr_pngs.generate_verified_png_folder(
            qr_pngs.validate_manifest_rows(manifest_rows()),
            output,
        )


@pytest.mark.parametrize("wrapped", [False, True])
def test_load_manifest_accepts_raw_or_success_wrapper(tmp_path, wrapped):
    rows = manifest_rows()
    payload = {"success": True, "data": rows} if wrapped else rows
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert qr_pngs.load_manifest(source) == qr_pngs.validate_manifest_rows(rows)


@pytest.mark.parametrize("field", ["access_token", "table_id", "hall_id"])
def test_manifest_rejects_sensitive_fields(field):
    rows = manifest_rows()
    rows[0][field] = "must-not-enter-the-generator"
    with pytest.raises(ValueError, match="sensitive"):
        qr_pngs.validate_manifest_rows(rows)
