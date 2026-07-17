# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "qrcode[pil]>=8,<9",
#   "Pillow>=11,<13",
#   "zxing-cpp>=2.2,<3",
# ]
# ///

import argparse
import csv
import json
import re
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

CODE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
SAFE_FIELDS = (
    "table_title",
    "hall_title",
    "service_percent",
    "manual_code",
    "start_param",
    "deep_link",
)


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must contain at least one table")

    validated: list[dict] = []
    seen_codes: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Manifest row is not an object")
        row = {field: raw.get(field) for field in SAFE_FIELDS}
        if not all(
            isinstance(row[field], str)
            for field in SAFE_FIELDS
            if field != "service_percent"
        ):
            raise ValueError("Manifest row has missing text fields")
        code = row["manual_code"]
        if CODE_RE.fullmatch(code) is None:
            raise ValueError(f"Invalid manual code: {code!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate manual code: {code}")

        parsed = urlparse(row["deep_link"])
        start_param = parse_qs(parsed.query).get("startapp", [None])[0]
        if parsed.scheme != "https" or parsed.netloc != "t.me":
            raise ValueError("Deep link must use https://t.me")
        if start_param != row["start_param"]:
            raise ValueError(f"Deep link/start parameter mismatch for table {code}")
        if not row["start_param"].startswith(f"t2_{code}_"):
            raise ValueError(f"Start parameter/code mismatch for table {code}")

        seen_codes.add(code)
        validated.append(row)

    return sorted(
        validated,
        key=lambda row: (
            row["hall_title"].casefold(),
            int(row["manual_code"]),
            row["table_title"].casefold(),
        ),
    )


def verify_api(rows: list[dict], api_base: str) -> None:
    endpoint = api_base.rstrip("/") + "/tables/resolve"
    for row in rows:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"code": row["manual_code"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        data = payload.get("data", {})
        safe_actual = (
            data.get("table_title"),
            data.get("hall_title"),
            data.get("manual_code"),
        )
        safe_expected = (
            row["table_title"],
            row["hall_title"],
            row["manual_code"],
        )
        if safe_actual != safe_expected:
            raise ValueError(
                f"Deployed resolver mismatch for table {row['manual_code']}"
            )


FONT_REGULAR_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
FONT_BOLD_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def _font_path(candidates: tuple[Path, ...]) -> Path:
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise RuntimeError("A supported Arial or DejaVu Sans font is required")
    return path


def _center(
    draw, text: str, font, y: int, width: int, fill: str = "#161616"
) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2, y), text, font=font, fill=fill)


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-").lower()
    return slug or "table"


def render_card(row: dict, destination: Path) -> None:
    width, height = 1200, 1500
    regular = _font_path(FONT_REGULAR_CANDIDATES)
    bold = _font_path(FONT_BOLD_CANDIDATES)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    _center(
        draw,
        "OLOT SOMSA",
        ImageFont.truetype(str(bold), 70),
        55,
        width,
        "#8F2D20",
    )
    _center(draw, row["hall_title"], ImageFont.truetype(str(regular), 42), 150, width)
    _center(draw, row["table_title"], ImageFont.truetype(str(bold), 76), 215, width)

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=18,
        border=4,
    )
    qr.add_data(row["deep_link"])
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_image.thumbnail((900, 900), Image.Resampling.NEAREST)
    canvas.paste(qr_image, ((width - qr_image.width) // 2, 330))

    _center(
        draw,
        "Stol raqami / Номер стола",
        ImageFont.truetype(str(regular), 42),
        1250,
        width,
    )
    _center(
        draw,
        row["manual_code"],
        ImageFont.truetype(str(bold), 112),
        1310,
        width,
        "#8F2D20",
    )
    canvas.save(destination, format="PNG", optimize=True)


def build_pdf(cards: list[Path], destination: Path) -> None:
    pages: list[Image.Image] = []
    page_width, page_height = 2480, 3508
    cell_width, cell_height = page_width // 2, page_height // 2
    for offset in range(0, len(cards), 4):
        page = Image.new("RGB", (page_width, page_height), "white")
        for index, path in enumerate(cards[offset : offset + 4]):
            card = Image.open(path).convert("RGB")
            card.thumbnail((1120, 1500), Image.Resampling.LANCZOS)
            column, row = index % 2, index // 2
            x = column * cell_width + (cell_width - card.width) // 2
            y = row * cell_height + (cell_height - card.height) // 2
            page.paste(card, (x, y))
        pages.append(page)
    pages[0].save(
        destination,
        "PDF",
        resolution=300,
        save_all=True,
        append_images=pages[1:],
    )


def generate_package(rows: list[dict], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    png_dir = output / "png"
    png_dir.mkdir()
    cards: list[Path] = []
    for row in rows:
        filename = (
            f"{int(row['manual_code']):06d}-"
            f"{_slug(row['hall_title'])}-{_slug(row['table_title'])}.png"
        )
        destination = png_dir / filename
        render_card(row, destination)
        decoded = zxingcpp.read_barcode(Image.open(destination))
        if decoded is None or decoded.text != row["deep_link"]:
            raise ValueError(f"QR decode mismatch for table {row['manual_code']}")
        cards.append(destination)

    (output / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output / "manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "verification.json").write_text(
        json.dumps({"verified_count": len(rows)}, indent=2) + "\n",
        encoding="utf-8",
    )
    build_pdf(cards, output / "all-table-qr-codes.pdf")

    zip_path = output.with_suffix(".zip")
    if zip_path.exists():
        raise FileExistsError(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output))
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-api")
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    if args.verify_api:
        verify_api(rows, args.verify_api)
    zip_path = generate_package(rows, args.output)
    print(f"verified_tables={len(rows)}")
    print(f"output_directory={args.output}")
    print(f"zip_archive={zip_path}")


if __name__ == "__main__":
    main()
