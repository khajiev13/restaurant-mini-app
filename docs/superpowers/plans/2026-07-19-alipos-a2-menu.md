# AliPOS A2 Restaurant Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate four accurate, print-ready A2 portrait color variants and full-resolution PNG previews from the current live AliPOS menu.

**Architecture:** A focused Python renderer reads the existing backend AliPOS client, normalizes display-only capitalization, downloads only the product images explicitly returned by AliPOS, and draws a single A2 page with ReportLab. Tests cover price formatting, lossless category grouping, and A2 page dimensions; Poppler rendering plus image inspection covers visual fidelity.

**Tech Stack:** Python 3.12, existing `backend/app/services/alipos_api.py`, ReportLab, Pillow, pypdf, Poppler (`pdftoppm`, `pdfinfo`).

## Global Constraints

- Finished size is A2 portrait, 420 x 594 mm.
- Final rendering is 300 DPI.
- Deliverables use `output/pdf/olot-somsa-menu-a2-<palette>.pdf` and `.png` for the `teal-gold`, `burgundy-cream`, `black-copper`, and `ivory-green` palettes.
- Use the live AliPOS composition and availability response, the existing OLOT SOMSA logo, AliPOS photos for 1 kg Osh and Mastava, and the approved generated Qovurma lagmon and Lag'mon assets.
- Include all 54 live AliPOS items exactly once with unchanged prices.
- Normalize only capitalization and punctuation; do not invent descriptions, ingredients, serving sizes, or availability.
- Keep credentials and tokens in process; do not print or embed them.
- Do not modify AliPOS or production application data.

---

### Task 1: Add the deterministic A2 menu renderer

**Files:**
- Create: `scripts/generate_alipos_a2_menu.py`
- Create: `scripts/test_generate_alipos_a2_menu.py`
- Create: `frontend/src/assets/menu/qovurma-lagmon-generated.png`
- Create: `frontend/src/assets/menu/lagmon-generated.png`

**Interfaces:**
- Consumes: `alipos_api.get_menu() -> dict`, `alipos_api.get_menu_availability() -> dict`, and `frontend/src/assets/logo.png`.
- Produces: `format_price(value: object) -> str`, `normalize_display_name(value: object) -> str`, `group_items(menu: dict) -> dict[str, list[dict]]`, and `build_menu_pdf(menu: dict, output_path: Path, cache_dir: Path) -> None`.

- [ ] **Step 1: Write unit tests for formatting, grouping, and A2 output**

Create tests equivalent to:

```python
from pathlib import Path

from pypdf import PdfReader

from generate_alipos_a2_menu import (
    build_menu_pdf,
    format_price,
    group_items,
    normalize_display_name,
)


def test_format_price_groups_uzs_thousands():
    assert format_price(35000.0) == "35 000"
    assert format_price("4000") == "4 000"


def test_normalize_display_name_changes_only_presentation():
    assert normalize_display_name("qora choy") == "Qora choy"
    assert normalize_display_name("cola 1,L") == "Cola 1 L"


def test_group_items_keeps_every_item_once():
    menu = {
        "categories": [
            {"id": "food", "name": "ovqat"},
            {"id": "tea", "name": "choy"},
        ],
        "items": [
            {"id": "1", "categoryId": "food", "name": "Osh", "price": 30000},
            {"id": "2", "categoryId": "tea", "name": "qora choy", "price": 4000},
        ],
    }
    grouped = group_items(menu)
    assert [item["id"] for items in grouped.values() for item in items] == ["1", "2"]


def test_build_menu_pdf_is_one_a2_portrait_page(tmp_path: Path):
    menu = {
        "categories": [{"id": "food", "name": "ovqat"}],
        "items": [{"id": "1", "categoryId": "food", "name": "Osh", "price": 30000}],
    }
    output = tmp_path / "menu.pdf"
    build_menu_pdf(menu, output, tmp_path / "images")
    page = PdfReader(str(output)).pages[0]
    assert len(PdfReader(str(output)).pages) == 1
    assert abs(float(page.mediabox.width) - 1190.55) < 0.6
    assert abs(float(page.mediabox.height) - 1683.78) < 0.6
```

- [ ] **Step 2: Run the focused tests and verify the renderer is missing**

Run:

```bash
PYTHONPATH=backend/.venv312/lib/python3.12/site-packages:scripts \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m pytest scripts/test_generate_alipos_a2_menu.py -q
```

Expected: collection fails because `generate_alipos_a2_menu` does not exist.

- [ ] **Step 3: Implement the smallest renderer that satisfies the design**

Implement these boundaries:

```python
PAGE_SIZE = A2
BACKGROUND = HexColor("#042f33")
PANEL = HexColor("#0a4143")
ORANGE = HexColor("#ef7f2c")
GOLD = HexColor("#f3c65f")
CREAM = HexColor("#fff6df")


def format_price(value: object) -> str:
    return f"{int(Decimal(str(value))):,}".replace(",", " ")


def normalize_display_name(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    text = re.sub(r"(?<=\d)[,.](?=[Ll]\b)", " ", text)
    return text[:1].upper() + text[1:] if text else text


def group_items(menu: dict) -> dict[str, list[dict]]:
    category_names = {
        str(category["id"]): str(category.get("name") or "Boshqa")
        for category in menu.get("categories", [])
    }
    grouped = {name: [] for name in category_names.values()}
    for item in menu.get("items", []):
        grouped.setdefault(category_names.get(str(item.get("categoryId")), "Boshqa"), []).append(item)
    return grouped
```

`build_menu_pdf` must draw one A2 portrait page with a deep-teal background, the existing square logo in the header, gold `MENYU` title, and four clear sections. `Ovqatlar` spans two columns; `Somsa`, `Choy va kofe`, and `Ichimliklar` occupy the right-side panels. Each row draws the normalized item name, a dotted leader, and the grouped price. Use only actual AliPOS image URLs, crop them without distortion, and omit an image on download failure.

The command-line entry point must:

```python
async def load_live_menu() -> dict:
    menu = await alipos_api.get_menu()
    availability = await alipos_api.get_menu_availability()
    if availability.get("items") or availability.get("modifiers"):
        print("AliPOS availability restrictions were returned; composition remains the menu source.")
    return menu


def main() -> None:
    output = Path("output/pdf/olot-somsa-menu-a2.pdf")
    menu = asyncio.run(load_live_menu())
    build_menu_pdf(menu, output, Path("tmp/pdfs/olot-somsa-a2/images"))
    print(f"Rendered {len(menu.get('items', []))} items to {output}")
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
PYTHONPATH=backend/.venv312/lib/python3.12/site-packages:scripts \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m pytest scripts/test_generate_alipos_a2_menu.py -q
```

Expected: four tests pass.

- [ ] **Step 5: Commit the renderer and tests**

```bash
git add scripts/generate_alipos_a2_menu.py scripts/test_generate_alipos_a2_menu.py
git commit -m "feat: generate AliPOS A2 menu"
```

### Task 2: Generate the current A2 menu artifacts

**Files:**
- Create: four `output/pdf/olot-somsa-menu-a2-<palette>.pdf` files
- Create: four `output/pdf/olot-somsa-menu-a2-<palette>.png` files
- Create temporarily: `tmp/pdfs/olot-somsa-a2/`

**Interfaces:**
- Consumes: the Task 1 CLI and process-only environment loaded from `.env`.
- Produces: four A2 PDFs and four 300 DPI PNGs with identical menu content and distinct palettes.

- [ ] **Step 1: Generate the PDF from a fresh AliPOS read**

Run from the repository root:

```bash
set -a
source .env
set +a
PYTHONPATH=backend/.venv312/lib/python3.12/site-packages:backend:scripts \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/generate_alipos_a2_menu.py
```

Expected: `Rendered 54 items to output/pdf/olot-somsa-menu-a2.pdf`; no token, credential, or raw AliPOS response is printed.

- [ ] **Step 2: Render a full-resolution 300 DPI PNG**

Run:

```bash
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm \
  -f 1 -singlefile -r 300 -png \
  output/pdf/olot-somsa-menu-a2.pdf \
  output/pdf/olot-somsa-menu-a2
```

Expected: `output/pdf/olot-somsa-menu-a2.png` is approximately 4961 x 7016 pixels.

- [ ] **Step 3: Confirm the PDF metadata and raster dimensions**

Run:

```bash
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdfinfo \
  output/pdf/olot-somsa-menu-a2.pdf
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -c 'from PIL import Image; im=Image.open("output/pdf/olot-somsa-menu-a2.png"); print(im.size)'
```

Expected: one A2 portrait page near `1190.55 x 1683.78 pts` and PNG dimensions near `(4961, 7016)`.

### Task 3: Verify content and visual quality

**Files:**
- Inspect: `output/pdf/olot-somsa-menu-a2.pdf`
- Inspect: `output/pdf/olot-somsa-menu-a2.png`

**Interfaces:**
- Consumes: Task 2 artifacts and the fresh in-process AliPOS menu.
- Produces: evidence that the menu is complete, accurate, and visually readable.

- [ ] **Step 1: Verify the artifact contains 54 unique menu rows and current prices**

Run a check that reloads the live composition, extracts text from the PDF with pypdf, and compares each normalized item name and formatted price against the rendered text. The check must print only aggregate results:

```text
categories=4
source_items=54
unique_source_ids=54
missing_names=0
missing_prices=0
```

Expected: every count matches exactly; do not print tokens or raw responses.

- [ ] **Step 2: Inspect the full-page PNG**

Open `output/pdf/olot-somsa-menu-a2.png` with the image viewer and check:

- no clipping or overlap;
- item text is readable at A2 scale;
- prices align consistently;
- all four sections are visually distinct;
- logo and photographs are sharp and undistorted;
- no fake food photography or unapproved copy appears.

- [ ] **Step 3: Iterate once if a defect is visible**

Change only the affected spacing, font size, color, or crop in `scripts/generate_alipos_a2_menu.py`; rerun Task 1 Step 4 and all of Task 2, then repeat Tasks 3 Steps 1-2.

- [ ] **Step 4: Report deliverables**

Provide clickable links to both final files and embed the PNG preview in the final response. State that the data was read from AliPOS without modifying it and report the verified item/category counts.
