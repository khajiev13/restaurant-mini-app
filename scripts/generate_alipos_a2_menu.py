"""Generate the print-ready OLOT SOMSA A2 menu from live AliPOS data."""

from __future__ import annotations

import asyncio
import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A2
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_SIZE = A2
BACKGROUND = HexColor("#042f33")
PANEL = HexColor("#0a4143")
PANEL_DARK = HexColor("#07383b")
ORANGE = HexColor("#ef7f2c")
GOLD = HexColor("#f3c65f")
CREAM = HexColor("#fff6df")
MUTED = HexColor("#b8d3cb")
LINE = HexColor("#2d6665")

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "frontend/src/assets/logo.png"


def format_price(value: object) -> str:
    """Format a numeric AliPOS price with grouped thousands."""
    return f"{int(Decimal(str(value))):,}".replace(",", " ")


def normalize_display_name(value: object) -> str:
    """Apply display-only whitespace, capitalization, and unit punctuation cleanup."""
    text = " ".join(str(value or "").strip().split())
    text = re.sub(r"(?<=\d)[,.](?=[Ll]\b)", " ", text)
    return text[:1].upper() + text[1:] if text else text


def group_items(menu: dict) -> dict[str, list[dict]]:
    """Group items by returned category without changing source order."""
    category_names = {
        str(category["id"]): str(category.get("name") or "Boshqa")
        for category in menu.get("categories", [])
    }
    grouped = {name: [] for name in category_names.values()}
    for item in menu.get("items", []):
        category = category_names.get(str(item.get("categoryId")), "Boshqa")
        grouped.setdefault(category, []).append(item)
    return grouped


def _category_items(grouped: dict[str, list[dict]], category_name: str) -> list[dict]:
    wanted = category_name.casefold()
    for name, items in grouped.items():
        if name.casefold() == wanted:
            return items
    return []


def _fit_font_size(text: str, font: str, maximum: float, width: float) -> float:
    size = maximum
    while size > 12 and stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _draw_panel(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill=PANEL,
) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(1.4)
    pdf.roundRect(x, y, width, height, 22, stroke=1, fill=1)


def _draw_section_header(
    pdf: canvas.Canvas,
    title: str,
    x: float,
    top: float,
    width: float,
    *,
    font_size: float = 24,
) -> None:
    pdf.setFillColor(ORANGE)
    pdf.roundRect(x, top - 48, width, 48, 15, stroke=0, fill=1)
    pdf.setFillColor(CREAM)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawString(x + 16, top - 33, title)


def _draw_item_row(
    pdf: canvas.Canvas,
    item: dict,
    x: float,
    baseline: float,
    width: float,
    *,
    name_size: float = 16,
    price_size: float = 15,
) -> None:
    name = normalize_display_name(item.get("name"))
    price = format_price(item.get("price", 0))
    price_width = stringWidth(price, "Helvetica-Bold", price_size)
    name_width = max(width - price_width - 30, 70)
    fitted_size = _fit_font_size(name, "Helvetica", name_size, name_width)

    pdf.setFillColor(CREAM)
    pdf.setFont("Helvetica", fitted_size)
    pdf.drawString(x, baseline, name)

    rendered_name_width = stringWidth(name, "Helvetica", fitted_size)
    dots_start = x + rendered_name_width + 8
    dots_end = x + width - price_width - 10
    if dots_end > dots_start:
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(1)
        pdf.setDash(1, 4)
        pdf.line(dots_start, baseline + 3, dots_end, baseline + 3)
        pdf.setDash()

    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica-Bold", price_size)
    pdf.drawRightString(x + width, baseline, price)


def _image_url(item: dict) -> str | None:
    images = item.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        return None
    value = first.get("url")
    return str(value) if value else None


def _download_image(item: dict, cache_dir: Path) -> Path | None:
    url = _image_url(item)
    if not url:
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    destination = cache_dir / f"{digest}.jpg"
    if destination.exists():
        return destination

    try:
        import httpx

        response = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "restaurant-mini-app-menu/1.0"},
        )
        response.raise_for_status()
        destination.write_bytes(response.content)
        with Image.open(destination) as image:
            image.verify()
    except Exception:  # noqa: BLE001 - a missing photo must not block the menu
        destination.unlink(missing_ok=True)
        return None
    return destination


def _prepare_image(
    source: Path,
    cache_dir: Path,
    width: int,
    height: int,
    *,
    radius: int,
) -> Path | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    prepared = cache_dir / f"{source.stem}-{width}x{height}-r{radius}.png"
    if prepared.exists():
        return prepared
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            fitted = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=radius,
            fill=255,
        )
        fitted.putalpha(mask)
        fitted.save(prepared, "PNG")
    except Exception:  # noqa: BLE001 - use the typography fallback
        prepared.unlink(missing_ok=True)
        return None
    return prepared


def _draw_photo(
    pdf: canvas.Canvas,
    item: dict,
    x: float,
    y: float,
    width: float,
    height: float,
    cache_dir: Path,
    *,
    caption: bool,
) -> bool:
    downloaded = _download_image(item, cache_dir)
    if not downloaded:
        return False
    prepared = _prepare_image(
        downloaded,
        cache_dir,
        max(int(width * 3), 300),
        max(int(height * 3), 300),
        radius=42,
    )
    if not prepared:
        return False

    pdf.drawImage(
        ImageReader(str(prepared)),
        x,
        y,
        width=width,
        height=height,
        mask="auto",
    )
    if caption:
        caption_text = normalize_display_name(item.get("name"))
        pdf.setFillColor(BACKGROUND)
        pdf.roundRect(x + 8, y + 8, width - 16, 27, 9, stroke=0, fill=1)
        pdf.setFillColor(CREAM)
        pdf.setFont("Helvetica-Bold", _fit_font_size(caption_text, "Helvetica-Bold", 12, width - 28))
        pdf.drawCentredString(x + width / 2, y + 17, caption_text)
    return True


def _select_photo_items(menu: dict, names: tuple[str, ...]) -> list[dict]:
    catalog = {str(item.get("name", "")).casefold(): item for item in menu.get("items", [])}
    selected: list[dict] = []
    for name in names:
        item = catalog.get(name.casefold())
        if item and _image_url(item):
            selected.append(item)
    if len(selected) < len(names):
        selected_ids = {str(item.get("id")) for item in selected}
        for item in menu.get("items", []):
            if _image_url(item) and str(item.get("id")) not in selected_ids:
                selected.append(item)
                selected_ids.add(str(item.get("id")))
            if len(selected) == len(names):
                break
    return selected


def _draw_header(pdf: canvas.Canvas, menu: dict, cache_dir: Path) -> None:
    page_width, page_height = PAGE_SIZE
    margin = 48
    header_y = page_height - 337
    header_height = 289

    _draw_panel(pdf, margin, header_y, page_width - 2 * margin, header_height, fill=PANEL_DARK)

    if LOGO_PATH.exists():
        pdf.drawImage(
            ImageReader(str(LOGO_PATH)),
            margin + 18,
            header_y + 18,
            width=252,
            height=252,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )

    title_x = margin + 300
    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica-Bold", 72)
    pdf.drawString(title_x, header_y + 174, "MENYU")
    pdf.setFillColor(ORANGE)
    pdf.roundRect(title_x, header_y + 130, 254, 30, 10, stroke=0, fill=1)
    pdf.setFillColor(CREAM)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(title_x + 127, header_y + 140, "NARXLAR SO'MDA")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 13)
    pdf.drawString(title_x, header_y + 93, "OLOT SOMSA")

    photo_items = _select_photo_items(menu, ("1 kg Osh", "Mastava", "Fri"))
    photo_size = 132
    photo_gap = 14
    photo_x = page_width - margin - (photo_size * 3 + photo_gap * 2) - 18
    photo_y = header_y + 81
    for index, item in enumerate(photo_items[:3]):
        _draw_photo(
            pdf,
            item,
            photo_x + index * (photo_size + photo_gap),
            photo_y,
            photo_size,
            photo_size,
            cache_dir,
            caption=True,
        )


def _draw_food_panel(
    pdf: canvas.Canvas,
    items: list[dict],
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    _draw_panel(pdf, x, y, width, height)
    _draw_section_header(pdf, "OVQATLAR", x + 18, y + height - 18, width - 36)

    split_at = (len(items) + 1) // 2
    columns = (items[:split_at], items[split_at:])
    inner_gap = 24
    inner_width = (width - 36 - inner_gap) / 2
    start_y = y + height - 101
    line_height = min(62, (height - 190) / max(split_at - 1, 1))
    for column_index, column_items in enumerate(columns):
        item_x = x + 18 + column_index * (inner_width + inner_gap)
        for row_index, item in enumerate(column_items):
            _draw_item_row(
                pdf,
                item,
                item_x,
                start_y - row_index * line_height,
                inner_width,
            )


def _draw_somsa_panel(
    pdf: canvas.Canvas,
    items: list[dict],
    x: float,
    y: float,
    width: float,
    height: float,
    cache_dir: Path,
) -> None:
    _draw_panel(pdf, x, y, width, height)
    _draw_section_header(pdf, "SOMSA", x + 18, y + height - 18, width - 36)
    if items:
        photo_height = max(height - 151, 90)
        drew_photo = _draw_photo(
            pdf,
            items[0],
            x + 18,
            y + 65,
            width - 36,
            photo_height,
            cache_dir,
            caption=False,
        )
        if not drew_photo:
            pdf.setFillColor(PANEL_DARK)
            pdf.roundRect(x + 18, y + 65, width - 36, photo_height, 16, stroke=0, fill=1)
        _draw_item_row(pdf, items[0], x + 20, y + 29, width - 40, name_size=17, price_size=16)


def _draw_list_panel(
    pdf: canvas.Canvas,
    title: str,
    items: list[dict],
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    _draw_panel(pdf, x, y, width, height)
    header_size = 21 if len(title) > 10 else 24
    _draw_section_header(pdf, title, x + 18, y + height - 18, width - 36, font_size=header_size)
    start_y = y + height - 101
    line_height = min(92, (height - 190) / max(len(items) - 1, 1))
    for row_index, item in enumerate(items):
        _draw_item_row(
            pdf,
            item,
            x + 20,
            start_y - row_index * line_height,
            width - 40,
            name_size=16,
            price_size=15,
        )


def build_menu_pdf(menu: dict, output_path: Path, cache_dir: Path) -> None:
    """Render one A2 portrait page from AliPOS composition data."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=PAGE_SIZE, pageCompression=1)
    pdf.setTitle("OLOT SOMSA - A2 menyu")
    pdf.setAuthor("OLOT SOMSA")
    page_width, page_height = PAGE_SIZE

    pdf.setFillColor(BACKGROUND)
    pdf.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(2)
    pdf.roundRect(24, 24, page_width - 48, page_height - 48, 28, stroke=1, fill=0)
    _draw_header(pdf, menu, cache_dir)

    grouped = group_items(menu)
    food = _category_items(grouped, "ovqat")
    somsa = _category_items(grouped, "Somsa")
    tea = _category_items(grouped, "choy")
    drinks = _category_items(grouped, "suvlar")

    assigned_ids = {
        str(item.get("id"))
        for collection in (food, somsa, tea, drinks)
        for item in collection
    }
    extras = [
        item
        for item in menu.get("items", [])
        if str(item.get("id")) not in assigned_ids
    ]
    food = [*food, *extras]

    margin = 48
    gap = 16
    content_y = 74
    content_top = page_height - 365
    content_height = content_top - content_y
    inner_width = page_width - 2 * margin
    column_width = (inner_width - 3 * gap) / 4
    food_width = 2 * column_width + gap
    third_x = margin + food_width + gap
    fourth_x = third_x + column_width + gap

    _draw_food_panel(pdf, food, margin, content_y, food_width, content_height)
    somsa_height = 402
    _draw_somsa_panel(
        pdf,
        somsa,
        third_x,
        content_top - somsa_height,
        column_width,
        somsa_height,
        cache_dir,
    )
    _draw_list_panel(
        pdf,
        "CHOY VA KOFE",
        tea,
        third_x,
        content_y,
        column_width,
        content_height - somsa_height - gap,
    )
    _draw_list_panel(
        pdf,
        "ICHIMLIKLAR",
        drinks,
        fourth_x,
        content_y,
        column_width,
        content_height,
    )

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(page_width / 2, 43, "Narxlar so'mda ko'rsatilgan")
    pdf.showPage()
    pdf.save()


async def load_live_menu() -> dict[str, Any]:
    """Read current composition and availability without exposing credentials."""
    from app.services import alipos_api

    menu = await alipos_api.get_menu()
    availability = await alipos_api.get_menu_availability()
    if availability.get("items") or availability.get("modifiers"):
        print("AliPOS availability restrictions were returned.")
    return menu


def main() -> None:
    output = ROOT / "output/pdf/olot-somsa-menu-a2.pdf"
    cache_dir = ROOT / "tmp/pdfs/olot-somsa-a2/images"
    menu = asyncio.run(load_live_menu())
    build_menu_pdf(menu, output, cache_dir)
    print(f"Rendered {len(menu.get('items', []))} items to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
