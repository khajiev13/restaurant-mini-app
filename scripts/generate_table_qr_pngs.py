import argparse
import json
import math
import re
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
import zxingcpp
from PIL import Image

CODE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
TITLE_CODE_RE = re.compile(r"([0-9]+)\s*$")
START_PARAM_RE = re.compile(
    r"^t2_((?:0|[1-9][0-9]{0,5}))_([A-Za-z0-9_-]{12})$"
)
REQUIRED_TEXT_FIELDS = (
    "table_title",
    "hall_title",
    "manual_code",
    "start_param",
    "deep_link",
)
SENSITIVE_FIELDS = {"access_token", "table_id", "hall_id", "jwt", "token"}
MIN_SIDE_PIXELS = 1200
QUIET_ZONE_MODULES = 4


def _title_code(title: str) -> str:
    match = TITLE_CODE_RE.search(title.strip())
    if match is None or not 1 <= len(match.group(1)) <= 6:
        raise ValueError("Table title has no valid trailing number")
    return str(int(match.group(1)))


def validate_manifest_rows(rows: object) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must contain at least one table")
    validated: list[dict] = []
    seen_codes: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Manifest row is not an object")
        if SENSITIVE_FIELDS.intersection(raw):
            raise ValueError("Manifest row contains a sensitive field")
        if any(not isinstance(raw.get(field), str) for field in REQUIRED_TEXT_FIELDS):
            raise ValueError("Manifest row has missing text fields")

        code = raw["manual_code"]
        if CODE_RE.fullmatch(code) is None:
            raise ValueError(f"Invalid manual code: {code!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate manual code: {code}")
        if _title_code(raw["table_title"]) != code:
            raise ValueError(f"Table title/code mismatch for table {code}")

        start_match = START_PARAM_RE.fullmatch(raw["start_param"])
        if start_match is None or start_match.group(1) != code:
            raise ValueError(f"Start parameter/code mismatch for table {code}")
        parsed = urlparse(raw["deep_link"])
        query = parse_qs(parsed.query, keep_blank_values=True)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "t.me"
            or not parsed.path.strip("/")
            or parsed.fragment
            or set(query) != {"startapp"}
            or query["startapp"] != [raw["start_param"]]
        ):
            raise ValueError(f"Deep link/start parameter mismatch for table {code}")

        seen_codes.add(code)
        validated.append({field: raw[field] for field in REQUIRED_TEXT_FIELDS})
    return sorted(validated, key=lambda row: int(row["manual_code"]))


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and payload.get("success") is not True:
        raise ValueError("Manifest response was not successful")
    return validate_manifest_rows(rows)


def _read_response(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=20) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("Deployed endpoint did not return HTTP 200")
        return response.read()


def verify_deployment(rows: list[dict], public_base: str) -> None:
    base = public_base.rstrip("/")
    for health_url in (f"{base}/healthz", f"{base}/api/health"):
        _read_response(urllib.request.Request(health_url, method="GET"))

    endpoint = f"{base}/api/tables/resolve"
    for row in rows:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"entry": row["start_param"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(_read_response(request))
        data = payload.get("data") if isinstance(payload, dict) else None
        actual = (
            data.get("manual_code") if isinstance(data, dict) else None,
            data.get("table_title") if isinstance(data, dict) else None,
        )
        expected = (row["manual_code"], row["table_title"])
        if (
            not isinstance(payload, dict)
            or payload.get("success") is not True
            or actual != expected
        ):
            raise ValueError(f"Deployed resolver mismatch for table {row['manual_code']}")


def render_raw_qr(deep_link: str) -> Image.Image:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=1,
        border=QUIET_ZONE_MODULES,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    total_modules = qr.modules_count + 2 * QUIET_ZONE_MODULES
    qr.box_size = math.ceil(MIN_SIDE_PIXELS / total_modules)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def generate_verified_png_folder(rows: list[dict], output: Path) -> Path:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".table-qr-", dir=output.parent) as temp_dir:
        staging = Path(temp_dir) / "delivery"
        staging.mkdir()
        for row in rows:
            destination = staging / f"table-{int(row['manual_code']):02d}.png"
            render_raw_qr(row["deep_link"]).save(
                destination, format="PNG", optimize=True
            )
            with Image.open(destination) as image:
                if (
                    image.format != "PNG"
                    or image.mode != "RGB"
                    or image.width != image.height
                    or image.width < MIN_SIDE_PIXELS
                ):
                    raise ValueError(f"Invalid PNG for table {row['manual_code']}")
                decoded = zxingcpp.read_barcode(image)
            if decoded is None or decoded.text != row["deep_link"]:
                raise ValueError(f"QR decode mismatch for table {row['manual_code']}")

        expected_names = {
            f"table-{int(row['manual_code']):02d}.png" for row in rows
        }
        actual_names = {path.name for path in staging.iterdir() if path.is_file()}
        if actual_names != expected_names or any(
            path.is_dir() for path in staging.iterdir()
        ):
            raise ValueError("PNG delivery folder contents do not match the manifest")
        staging.replace(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--public-base", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    verify_deployment(rows, args.public_base)
    output = generate_verified_png_folder(rows, args.output)
    print(f"verified_pngs={len(rows)}")
    print(f"output_directory={output}")


if __name__ == "__main__":
    main()
