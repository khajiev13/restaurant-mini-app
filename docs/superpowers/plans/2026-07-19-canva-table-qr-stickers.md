# Canva Table QR Stickers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one editable 29-page Canva design and one independently verified print-ready A7 PDF for the existing OLOT SOMSA production table QR codes.

**Architecture:** A focused Python generator discovers and validates the 29 source QR PNGs, renders a self-contained multi-page HTML artifact for direct Canva import, and renders an exact-size PDF using the same ordered page model. The HTML embeds the private local image bytes as data URIs, so the Canva import can use the platform's direct local-file path without publishing the QR assets. Independent PDF rendering and QR decoding verify that every printed page retains the exact source payload.

**Tech Stack:** Python 3.12, Pillow, ReportLab, pypdf, zxing-cpp, pytest, Poppler `pdftoppm`, HTML/CSS, Canva connector tools.

## Global Constraints

- Finished page size is exactly `74 × 105 mm`, portrait.
- The QR is exactly `62 × 62 mm`, including its original white quiet zone.
- Use exactly 29 source PNGs: tables `01–08` and `10–30`; never fabricate table `09`.
- Preserve every source QR PNG's square aspect ratio, colors, and quiet zone; never crop, recolor, round, mask, distort, compress, stylize, or overlay it.
- Use the fixed visible copy and order: `Buyurtma berish uchun skanerlang`, `Сканируйте, чтобы заказать`, `Scan to order`, `扫码点餐`.
- Use only `#FFFFFF`, `#101314`, `#07393D`, and `#F47B20` in the sticker artwork.
- Keep at least `4 mm` of finished-size safe margin and use a pure white page background.
- Do not publish the local QR PNGs to a public URL or file-sharing service.
- Do not change table numbers, manual codes, AliPOS IDs, QR payloads, or application behavior.
- The Canva deliverable is editable; the local PDF is the source of truth for exact physical print dimensions.
- The source design is `docs/superpowers/specs/2026-07-19-canva-table-qr-stickers-design.md`.

## File Map

- Create `scripts/generate_table_qr_sticker_package.py`: discover the approved source batch, render Canva-import HTML and exact-size PDF, render PDF previews, decode every output QR, and write a secret-safe verification report.
- Create `tests/scripts/test_generate_table_qr_sticker_package.py`: contract tests for inventory, HTML page structure/copy, PDF geometry, and full QR round-trip verification.
- Create `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/canva-table-qr-stickers.html`: self-contained 29-page Canva import artifact.
- Create `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/olot-somsa-table-qr-stickers-a7.pdf`: exact-size, print-ready 29-page PDF.
- Create `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/previews/`: one 300-DPI rendered PNG per PDF page.
- Create `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/verification.json`: page geometry, table mapping, file hashes, and payload hashes without raw QR URLs.

---

### Task 1: Build the deterministic sticker package generator

**Files:**
- Create: `scripts/generate_table_qr_sticker_package.py`
- Create: `tests/scripts/test_generate_table_qr_sticker_package.py`

**Interfaces:**
- Consumes: source directory containing `table-NN.png` files and a destination directory.
- Produces: `StickerPage`, `discover_pages(source_dir: Path) -> tuple[StickerPage, ...]`, `render_canva_html(pages, destination)`, `render_pdf(pages, destination)`, and `generate_package(source_dir, output_dir) -> dict[str, object]`.
- Command line: `python scripts/generate_table_qr_sticker_package.py --source <dir> --output <dir>`.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/scripts/test_generate_table_qr_sticker_package.py`:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_table_qr_sticker_package.py"
SOURCE = Path(
    "/Users/khajievroma/.codex/visualizations/2026/07/18/"
    "019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs"
)


def load_generator():
    spec = importlib.util.spec_from_file_location("table_qr_stickers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_discovers_exact_production_inventory():
    module = load_generator()
    pages = module.discover_pages(SOURCE)
    assert tuple(page.table_number for page in pages) == (
        *range(1, 9),
        *range(10, 31),
    )
    assert len(pages) == 29
    assert all(page.path.name == f"table-{page.table_number:02d}.png" for page in pages)
    assert all(page.source_payload for page in pages)


def test_canva_html_has_exact_pages_copy_and_embedded_qrs(tmp_path: Path):
    module = load_generator()
    pages = module.discover_pages(SOURCE)
    destination = tmp_path / "canva-table-qr-stickers.html"
    module.render_canva_html(pages, destination)
    html = destination.read_text(encoding="utf-8")

    assert html.count('data-document-role="page"') == 29
    assert html.count("data:image/png;base64,") == 29
    assert html.count("Buyurtma berish uchun skanerlang") == 29
    assert html.count("Сканируйте, чтобы заказать") == 29
    assert html.count("Scan to order") == 29
    assert html.count("扫码点餐") == 29
    assert 'data-label="Table 09"' not in html
    for table_number in (*range(1, 9), *range(10, 31)):
        assert html.count(f'data-label="Table {table_number:02d}"') == 1


def test_pdf_has_exact_page_count_and_a7_geometry(tmp_path: Path):
    module = load_generator()
    pages = module.discover_pages(SOURCE)
    destination = tmp_path / "stickers.pdf"
    module.render_pdf(pages, destination)

    reader = PdfReader(destination)
    assert len(reader.pages) == 29
    expected_width = module.mm(74)
    expected_height = module.mm(105)
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert abs(width - expected_width) < 0.05
        assert abs(height - expected_height) < 0.05


def test_full_package_round_trips_every_qr(tmp_path: Path):
    module = load_generator()
    report = module.generate_package(SOURCE, tmp_path)

    assert report["page_count"] == 29
    assert report["page_size_mm"] == [74, 105]
    assert report["qr_size_mm"] == [62, 62]
    assert report["tables"] == [*range(1, 9), *range(10, 31)]
    assert all(page["decoded_matches_source"] for page in report["pages"])
    assert all("source_payload" not in page for page in report["pages"])
    assert all("rendered_payload" not in page for page in report["pages"])

    saved = json.loads((tmp_path / "verification.json").read_text(encoding="utf-8"))
    assert saved == report
```

- [ ] **Step 2: Run the tests and verify the generator is absent**

Run:

```bash
uv run --no-project --python 3.12 \
  --with 'pytest>=9,<10' \
  --with 'Pillow>=11,<13' \
  --with 'reportlab>=4.4,<5' \
  --with 'pypdf>=6,<7' \
  --with 'zxing-cpp>=2.2,<3' \
  pytest tests/scripts/test_generate_table_qr_sticker_package.py -q
```

Expected: FAIL because `scripts/generate_table_qr_sticker_package.py` does not exist.

- [ ] **Step 3: Implement the generator**

Create `scripts/generate_table_qr_sticker_package.py`:

```python
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import zxingcpp
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


EXPECTED_TABLES = (*range(1, 9), *range(10, 31))
PAGE_WIDTH_MM = 74
PAGE_HEIGHT_MM = 105
QR_SIZE_MM = 62
PNG_PATTERN = re.compile(r"table-(\d{2})\.png")
UZBEK = "Buyurtma berish uchun skanerlang"
RUSSIAN = "Сканируйте, чтобы заказать"
ENGLISH = "Scan to order"
CHINESE = "扫码点餐"
WHITE = "#FFFFFF"
NEAR_BLACK = "#101314"
TEAL = "#07393D"
ORANGE = "#F47B20"
GRAY = "#7C8583"
ARIAL = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
ARIAL_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
ARIAL_UNICODE = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")


def mm(value: float) -> float:
    return value * 72 / 25.4


@dataclass(frozen=True)
class StickerPage:
    table_number: int
    path: Path
    source_payload: str
    source_sha256: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def decode_qr(path: Path) -> str:
    with Image.open(path) as image:
        decoded = zxingcpp.read_barcode(image)
    if decoded is None or not decoded.text:
        raise ValueError(f"QR did not decode: {path}")
    return decoded.text


def discover_pages(source_dir: Path) -> tuple[StickerPage, ...]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"QR source directory does not exist: {source_dir}")

    files = sorted(source_dir.glob("table-*.png"))
    parsed: dict[int, Path] = {}
    for path in files:
        match = PNG_PATTERN.fullmatch(path.name)
        if match is None:
            raise ValueError(f"Unexpected QR filename: {path.name}")
        table_number = int(match.group(1))
        if table_number in parsed:
            raise ValueError(f"Duplicate QR for table {table_number:02d}")
        with Image.open(path) as image:
            if image.width != image.height:
                raise ValueError(f"QR must be square: {path}")
            if image.width < 744:
                raise ValueError(f"QR is too small for 62 mm output: {path}")
        parsed[table_number] = path

    if tuple(sorted(parsed)) != EXPECTED_TABLES:
        raise ValueError(
            f"Expected tables {EXPECTED_TABLES}, found {tuple(sorted(parsed))}"
        )

    pages = []
    for table_number in EXPECTED_TABLES:
        path = parsed[table_number]
        source_bytes = path.read_bytes()
        pages.append(
            StickerPage(
                table_number=table_number,
                path=path,
                source_payload=decode_qr(path),
                source_sha256=sha256_bytes(source_bytes),
            )
        )
    return tuple(pages)


def qr_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_canva_html(pages: tuple[StickerPage, ...], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    page_markup = []
    for page in pages:
        number = f"{page.table_number:02d}"
        page_markup.append(
            f'''<section class="sticker" data-document-role="page" data-label="Table {number}">
  <div class="brand">OLOT SOMSA</div>
  <div class="table-number"><small>TABLE</small><strong>{number}</strong></div>
  <img class="qr" alt="Table {number} QR code" src="{qr_data_uri(page.path)}">
  <div class="accent"></div>
  <div class="copy uz">{UZBEK}</div>
  <div class="copy ru">{RUSSIAN}</div>
  <div class="copy en">{ENGLISH}</div>
  <div class="copy zh">{CHINESE}</div>
  <div class="footer">OLOT SOMSA • TABLE ORDERING</div>
</section>'''
        )

    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OLOT SOMSA Table QR Stickers</title>
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: {WHITE}; }}
.sticker {{
  position: relative; width: 888px; height: 1260px; overflow: hidden;
  background: {WHITE}; color: {NEAR_BLACK}; page-break-after: always;
  font-family: Arial, "Arial Unicode MS", "PingFang SC", "Microsoft YaHei", sans-serif;
}}
.brand {{ position: absolute; left: 72px; top: 58px; color: {TEAL}; font-size: 30px; font-weight: 800; letter-spacing: 4px; }}
.table-number {{ position: absolute; right: 72px; top: 52px; display: flex; align-items: flex-start; gap: 10px; }}
.table-number small {{ color: {GRAY}; font-size: 15px; font-weight: 700; letter-spacing: 1px; padding-top: 12px; }}
.table-number strong {{ color: {NEAR_BLACK}; font-size: 68px; line-height: .9; font-weight: 900; letter-spacing: -2px; }}
.qr {{ position: absolute; left: 72px; top: 156px; width: 744px; height: 744px; object-fit: contain; background: {WHITE}; }}
.accent {{ position: absolute; left: 393px; top: 936px; width: 102px; height: 12px; border-radius: 999px; background: {ORANGE}; }}
.copy {{ position: absolute; left: 48px; width: 792px; text-align: center; white-space: nowrap; }}
.uz {{ top: 974px; font-size: 28px; font-weight: 500; }}
.ru {{ top: 1015px; font-size: 28px; font-weight: 500; }}
.en {{ top: 1057px; color: {TEAL}; font-size: 30px; font-weight: 800; }}
.zh {{ top: 1102px; color: {NEAR_BLACK}; font-size: 44px; font-weight: 900; letter-spacing: 3px; }}
.footer {{ position: absolute; left: 0; right: 0; bottom: 52px; color: {GRAY}; text-align: center; font-size: 12px; letter-spacing: 2px; }}
</style>
</head>
<body>
{''.join(page_markup)}
</body>
</html>
'''
    destination.write_text(html, encoding="utf-8")


def register_fonts() -> None:
    for path in (ARIAL, ARIAL_BOLD, ARIAL_UNICODE):
        if not path.is_file():
            raise FileNotFoundError(f"Required font is missing: {path}")
    pdfmetrics.registerFont(TTFont("Arial", str(ARIAL)))
    pdfmetrics.registerFont(TTFont("ArialBold", str(ARIAL_BOLD)))
    pdfmetrics.registerFont(TTFont("ArialUnicode", str(ARIAL_UNICODE)))


def draw_centered_stroked_text(
    pdf: canvas.Canvas,
    text: str,
    font: str,
    size: float,
    center_x: float,
    baseline_y: float,
    color: str,
) -> None:
    width = pdfmetrics.stringWidth(text, font, size)
    text_object = pdf.beginText(center_x - width / 2, baseline_y)
    text_object.setFont(font, size)
    text_object.setFillColor(HexColor(color))
    text_object.setStrokeColor(HexColor(color))
    text_object.setTextRenderMode(2)
    pdf.setLineWidth(0.16)
    text_object.textLine(text)
    pdf.drawText(text_object)


def render_pdf(pages: tuple[StickerPage, ...], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    register_fonts()
    pdf = canvas.Canvas(
        str(destination),
        pagesize=(mm(PAGE_WIDTH_MM), mm(PAGE_HEIGHT_MM)),
        pageCompression=1,
    )
    center_x = mm(PAGE_WIDTH_MM / 2)
    for page in pages:
        number = f"{page.table_number:02d}"
        pdf.setFillColor(HexColor(WHITE))
        pdf.rect(0, 0, mm(PAGE_WIDTH_MM), mm(PAGE_HEIGHT_MM), fill=1, stroke=0)

        pdf.setFillColor(HexColor(TEAL))
        pdf.setFont("ArialBold", 8.7)
        pdf.drawString(mm(6), mm(97), "OLOT SOMSA")

        pdf.setFillColor(HexColor(GRAY))
        pdf.setFont("ArialBold", 4.8)
        pdf.drawRightString(mm(54.5), mm(98.1), "TABLE")
        pdf.setFillColor(HexColor(NEAR_BLACK))
        pdf.setFont("ArialBold", 19.5)
        pdf.drawRightString(mm(68), mm(94.8), number)

        pdf.drawImage(
            ImageReader(str(page.path)),
            mm(6),
            mm(30),
            width=mm(QR_SIZE_MM),
            height=mm(QR_SIZE_MM),
            preserveAspectRatio=True,
            mask=None,
        )

        pdf.setFillColor(HexColor(ORANGE))
        pdf.roundRect(mm(32.75), mm(27), mm(8.5), mm(0.9), mm(0.45), fill=1, stroke=0)

        pdf.setFillColor(HexColor(NEAR_BLACK))
        pdf.setFont("ArialUnicode", 7.4)
        pdf.drawCentredString(center_x, mm(23.2), UZBEK)
        pdf.drawCentredString(center_x, mm(19.9), RUSSIAN)
        pdf.setFillColor(HexColor(TEAL))
        pdf.setFont("ArialBold", 8.0)
        pdf.drawCentredString(center_x, mm(16.4), ENGLISH)
        draw_centered_stroked_text(
            pdf,
            CHINESE,
            "ArialUnicode",
            12.2,
            center_x,
            mm(11.4),
            NEAR_BLACK,
        )

        pdf.setFillColor(HexColor(GRAY))
        pdf.setFont("Arial", 3.6)
        pdf.drawCentredString(center_x, mm(4.4), "OLOT SOMSA • TABLE ORDERING")
        pdf.showPage()
    pdf.save()


def verify_pdf_geometry(pdf_path: Path, page_count: int) -> None:
    reader = PdfReader(pdf_path)
    if len(reader.pages) != page_count:
        raise ValueError(f"Expected {page_count} PDF pages, found {len(reader.pages)}")
    expected_width = mm(PAGE_WIDTH_MM)
    expected_height = mm(PAGE_HEIGHT_MM)
    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if abs(width - expected_width) >= 0.05 or abs(height - expected_height) >= 0.05:
            raise ValueError(f"Page {index} has unexpected geometry: {width} × {height}")


def render_pdf_previews(pdf_path: Path, preview_dir: Path) -> tuple[Path, ...]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    prefix = preview_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "300", str(pdf_path), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = tuple(sorted(preview_dir.glob("page-*.png")))
    if len(rendered) != 29:
        raise ValueError(f"Expected 29 rendered previews, found {len(rendered)}")
    return rendered


def generate_package(source_dir: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = discover_pages(source_dir)
    html_path = output_dir / "canva-table-qr-stickers.html"
    pdf_path = output_dir / "olot-somsa-table-qr-stickers-a7.pdf"
    preview_dir = output_dir / "previews"
    render_canva_html(pages, html_path)
    render_pdf(pages, pdf_path)
    verify_pdf_geometry(pdf_path, len(pages))
    rendered = render_pdf_previews(pdf_path, preview_dir)

    page_reports = []
    for page, preview_path in zip(pages, rendered, strict=True):
        rendered_payload = decode_qr(preview_path)
        page_reports.append(
            {
                "table": page.table_number,
                "source_file": page.path.name,
                "source_sha256": page.source_sha256,
                "payload_sha256": sha256_text(page.source_payload),
                "preview_file": preview_path.name,
                "decoded_matches_source": rendered_payload == page.source_payload,
            }
        )
    if not all(page["decoded_matches_source"] for page in page_reports):
        raise ValueError("At least one rendered QR does not match its source payload")

    report: dict[str, object] = {
        "page_count": len(pages),
        "page_size_mm": [PAGE_WIDTH_MM, PAGE_HEIGHT_MM],
        "qr_size_mm": [QR_SIZE_MM, QR_SIZE_MM],
        "tables": [page.table_number for page in pages],
        "html_file": html_path.name,
        "pdf_file": pdf_path.name,
        "pages": page_reports,
    }
    (output_dir / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = generate_package(args.source, args.output)
    print(
        f"Generated {report['page_count']} verified A7 table QR stickers in "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the focused tests and verify all contracts pass**

Run the same `uv run` command from Step 2.

Expected: `4 passed`; the integration test renders 29 PDF pages and every rendered QR matches its source payload.

- [ ] **Step 5: Commit the reusable generator and tests**

```bash
git add scripts/generate_table_qr_sticker_package.py tests/scripts/test_generate_table_qr_sticker_package.py
git commit -m "feat: generate verified Canva table QR sticker package"
```

---

### Task 2: Generate and visually inspect the production artifact package

**Files:**
- Read: `/Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs/table-*.png`
- Create: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/canva-table-qr-stickers.html`
- Create: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/olot-somsa-table-qr-stickers-a7.pdf`
- Create: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/previews/page-*.png`
- Create: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/verification.json`

**Interfaces:**
- Consumes: the generator from Task 1 and the 29 source QR PNGs.
- Produces: the exact local artifacts that Task 3 imports into Canva and that final handoff delivers to the user.

- [ ] **Step 1: Generate the production package**

Run:

```bash
uv run --no-project --python 3.12 \
  --with 'Pillow>=11,<13' \
  --with 'reportlab>=4.4,<5' \
  --with 'pypdf>=6,<7' \
  --with 'zxing-cpp>=2.2,<3' \
  python scripts/generate_table_qr_sticker_package.py \
  --source /Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs \
  --output /Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers
```

Expected: `Generated 29 verified A7 table QR stickers` and exit code `0`.

- [ ] **Step 2: Check the secret-safe verification summary**

Run:

```bash
python3 -c 'import json, pathlib; p=pathlib.Path("/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/verification.json"); r=json.loads(p.read_text()); print(r["page_count"], r["page_size_mm"], r["qr_size_mm"], r["tables"], all(x["decoded_matches_source"] for x in r["pages"]))'
```

Expected: `29 [74, 105] [62, 62] [1, 2, 3, 4, 5, 6, 7, 8, 10, ..., 30] True`. The report must contain only hashes, filenames, dimensions, table numbers, and booleans; it must not contain raw QR URLs.

- [ ] **Step 3: Render and inspect representative pages**

Use the PDF skill's render-and-verify workflow to inspect:

- `previews/page-01.png` for table `01`;
- `previews/page-15.png` for table `16`;
- `previews/page-29.png` for table `30`.

Expected: all three use the approved Clean Minimal layout, show the correct table number, contain all four lines without clipping, preserve a pure white QR area, and have no content crossing the page edge.

- [ ] **Step 4: Re-run the focused generator tests after production generation**

Run the Task 1 test command again.

Expected: `4 passed`.

---

### Task 3: Import and audit the editable 29-page Canva design

**Files:**
- Read: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/canva-table-qr-stickers.html`
- Read: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/verification.json`

**Interfaces:**
- Consumes: the self-contained HTML artifact generated in Task 2.
- Produces: a Canva design ID and edit/view URLs for `OLOT SOMSA — Table QR Stickers (A7, 29 pages)`.

- [ ] **Step 1: Import the generated HTML directly into Canva**

Call `canva_import_design_from_url` with:

```json
{
  "design_file": "/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/canva-table-qr-stickers.html",
  "intended_design_type": "other",
  "name": "OLOT SOMSA — Table QR Stickers (A7, 29 pages)",
  "user_intent": "Import the approved 29-page A7 OLOT SOMSA table QR sticker design as editable Canva pages."
}
```

Expected: a new Canva design with a design ID beginning with `D` and an edit/view URL. Do not use a public URL and do not upload the source PNG folder separately.

- [ ] **Step 2: Confirm design metadata and exact page count**

Call `canva_get_design` with the returned design ID, then call `canva_get_design_pages` with `offset: 1` and `limit: 29`.

Expected: title `OLOT SOMSA — Table QR Stickers (A7, 29 pages)` and exactly 29 pages. Page labels or visible thumbnails follow `01–08, 10–30`.

- [ ] **Step 3: Audit visible text content**

Call `canva_get_design_content` with the returned design ID.

Expected: every page contains `OLOT SOMSA`, its matching `TABLE NN`, and exactly one occurrence each of the four approved instruction lines. There is no `TABLE 09`.

- [ ] **Step 4: Review representative Canva thumbnails**

Call `canva_get_design_pages` three times with `limit: 1` and offsets `1`, `15`, and `29`. Show every returned thumbnail to the user.

Expected: the Canva pages visually match the approved local PDF for tables `01`, `16`, and `30`; QR images are square and unobstructed, copy is not clipped, and the orange divider is the only decorative accent.

- [ ] **Step 5: Handle any import drift without overwriting the approved design**

If Canva import visibly changes spacing, typography, table mapping, or QR geometry, do not start an editing transaction on the accepted design. Correct the deterministic HTML generator, repeat Tasks 1 and 2, and import a fresh Canva design. Keep only the Canva design whose representative thumbnails match the approved local previews.

Expected: no draft editing transaction remains open, and the final Canva URL points to the visually accepted 29-page design.

---

### Task 4: Final verification and handoff

**Files:**
- Read: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/olot-somsa-table-qr-stickers-a7.pdf`
- Read: `/Users/khajievroma/.codex/visualizations/2026/07/19/019f7a1b-e163-7561-97f6-bed827e0c251/table-qr-stickers/verification.json`

**Interfaces:**
- Consumes: the verified local artifact package and accepted Canva design URL.
- Produces: user handoff with Canva edit link, print-ready PDF link, and concise evidence summary.

- [ ] **Step 1: Run the final local verification command**

Run the Task 1 focused test command and the Task 2 verification-summary command one final time.

Expected: `4 passed`, page count `29`, page size `[74, 105]`, QR size `[62, 62]`, and all decode comparisons `True`.

- [ ] **Step 2: Confirm the PDF opens and representative pages render**

Use the PDF skill to render pages `1`, `15`, and `29` from the final PDF and compare them to the accepted Canva thumbnails.

Expected: table numbers and copy match; the local PDF retains exact A7 geometry and no scan-critical QR changes.

- [ ] **Step 3: Deliver both outputs**

Provide:

- the final Canva edit/view URL;
- a clickable local link to `olot-somsa-table-qr-stickers-a7.pdf`;
- page count `29` and table sequence `01–08, 10–30`;
- physical dimensions `74 × 105 mm` and QR dimensions `62 × 62 mm`;
- confirmation that all 29 PDF-rendered QRs decoded to the same payloads as their source PNGs.

Do not claim Canva exported the PDF; state that the exact-size print PDF was generated and verified independently from the same ordered source batch.
