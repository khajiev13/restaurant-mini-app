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
import math
import re
import urllib.request
import zipfile
from pathlib import Path

import qrcode
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

CODE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
START_PARAM_RE = re.compile(r"^t2_((?:0|[1-9][0-9]{0,5}))_([A-Za-z0-9_-]{12})$")
DEEP_LINK_RE = re.compile(
    r"https://t\.me/[A-Za-z0-9_]+\?startapp="
    r"(t2_(?:0|[1-9][0-9]{0,5})_[A-Za-z0-9_-]{12})"
)
SAFE_FIELDS = (
    "table_title",
    "hall_title",
    "service_percent",
    "manual_code",
    "start_param",
    "deep_link",
)


def _valid_service_percent(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 100
        and math.isfinite(value)
    )


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if payload.get("success") is not True or not isinstance(
            payload.get("data"), list
        ):
            raise ValueError("Manifest envelope must have success=true and array data")
        rows = payload["data"]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("Manifest must be an API envelope or raw array")
    if not rows:
        raise ValueError("Manifest must contain at least one table")

    validated: list[dict] = []
    seen_codes: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Manifest row is not an object")
        row = {field: raw.get(field) for field in SAFE_FIELDS}
        if not all(
            isinstance(row[field], str) and bool(row[field])
            for field in SAFE_FIELDS
            if field != "service_percent"
        ):
            raise ValueError("Manifest row has missing text fields")
        if not _valid_service_percent(row["service_percent"]):
            raise ValueError("Manifest row has invalid service_percent")
        code = row["manual_code"]
        if CODE_RE.fullmatch(code) is None:
            raise ValueError(f"Invalid manual code: {code!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate manual code: {code}")

        start_match = START_PARAM_RE.fullmatch(row["start_param"])
        if start_match is None or start_match.group(1) != code:
            raise ValueError(f"Invalid start parameter for table {code}")
        deep_link_match = DEEP_LINK_RE.fullmatch(row["deep_link"])
        if deep_link_match is None or deep_link_match.group(1) != row["start_param"]:
            raise ValueError(f"Deep link is invalid or mismatched for table {code}")

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


def _validate_resolver_response(payload, row: dict) -> None:
    if (
        not isinstance(payload, dict)
        or payload.get("success") is not True
        or not isinstance(payload.get("data"), dict)
    ):
        raise ValueError(
            f"Malformed deployed resolver response for table {row['manual_code']}"
        )
    data = payload["data"]
    if not all(
        isinstance(data.get(field), str) and bool(data[field])
        for field in ("table_title", "hall_title", "manual_code", "access_token")
    ) or not _valid_service_percent(data.get("service_percent")):
        raise ValueError(
            f"Malformed deployed resolver response for table {row['manual_code']}"
        )
    if CODE_RE.fullmatch(data["manual_code"]) is None:
        raise ValueError(
            f"Malformed deployed resolver response for table {row['manual_code']}"
        )
    safe_actual = (
        data["table_title"],
        data["hall_title"],
        data["service_percent"],
        data["manual_code"],
    )
    safe_expected = (
        row["table_title"],
        row["hall_title"],
        row["service_percent"],
        row["manual_code"],
    )
    if safe_actual != safe_expected:
        raise ValueError(f"Deployed resolver mismatch for table {row['manual_code']}")


def verify_api(rows: list[dict], api_base: str) -> None:
    endpoint = api_base.rstrip("/") + "/tables/resolve"
    for row in rows:
        for body in (
            {"entry": row["start_param"]},
            {"code": row["manual_code"]},
        ):
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            _validate_resolver_response(payload, row)


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


def _center(draw, text: str, font, y: int, width: int, fill: str = "#161616") -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2, y), text, font=font, fill=fill)


def _text_width(draw, text: str, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    remaining = " ".join(text.split())
    lines: list[str] = []
    while remaining:
        if _text_width(draw, remaining, font) <= max_width:
            lines.append(remaining)
            break
        end = 1
        while (
            end <= len(remaining)
            and _text_width(draw, remaining[:end], font) <= max_width
        ):
            end += 1
        prefix = remaining[: end - 1]
        word_break = prefix.rfind(" ")
        if word_break > 0:
            lines.append(prefix[:word_break])
            remaining = remaining[word_break + 1 :].lstrip()
        else:
            lines.append(prefix)
            remaining = remaining[len(prefix) :].lstrip()
    return lines


def _truncate_line(draw, text: str, font, max_width: int) -> str:
    suffix = "..."
    value = text.rstrip()
    while value and _text_width(draw, value + suffix, font) > max_width:
        value = value[:-1].rstrip()
    return value + suffix


def _draw_fitted_text(
    draw,
    text: str,
    font_path: Path,
    box: tuple[int, int, int, int],
    max_font_size: int,
    min_font_size: int,
    max_lines: int,
    fill: str = "#161616",
) -> None:
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    for size in range(max_font_size, min_font_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        lines = _wrap_text(draw, text, font, max_width)
        spacing = max(4, size // 8)
        block = "\n".join(lines)
        bounds = draw.multiline_textbbox(
            (0, 0), block, font=font, spacing=spacing, align="center"
        )
        if len(lines) <= max_lines and bounds[3] - bounds[1] <= max_height:
            break
    else:
        font = ImageFont.truetype(str(font_path), min_font_size)
        spacing = max(4, min_font_size // 8)
        lines = _wrap_text(draw, text, font, max_width)
        if len(lines) > max_lines:
            lines = [
                *lines[: max_lines - 1],
                _truncate_line(
                    draw,
                    " ".join(lines[max_lines - 1 :]),
                    font,
                    max_width,
                ),
            ]
        block = "\n".join(lines)
        bounds = draw.multiline_textbbox(
            (0, 0), block, font=font, spacing=spacing, align="center"
        )

    block_width = bounds[2] - bounds[0]
    block_height = bounds[3] - bounds[1]
    x = left + (max_width - block_width) / 2 - bounds[0]
    y = top + (max_height - block_height) / 2 - bounds[1]
    draw.multiline_text(
        (x, y),
        block,
        font=font,
        fill=fill,
        spacing=spacing,
        align="center",
    )


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
    _draw_fitted_text(
        draw,
        row["hall_title"],
        regular,
        (80, 140, 1120, 205),
        42,
        22,
        2,
    )
    _draw_fitted_text(
        draw,
        row["table_title"],
        bold,
        (80, 205, 1120, 320),
        76,
        32,
        2,
    )

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
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "verification.json").write_text(
        json.dumps({"verified_count": len(rows)}, indent=2) + "\n",
        encoding="utf-8",
    )
    build_pdf(cards, output / "all-table-qr-codes.pdf")

    zip_path = Path(f"{output}.zip")
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
