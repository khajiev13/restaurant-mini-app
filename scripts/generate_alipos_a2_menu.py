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
PALETTES = {
    "teal-gold": {
        "background": HexColor("#042f33"),
        "panel": HexColor("#0a4143"),
        "panel_dark": HexColor("#07383b"),
        "accent": HexColor("#ef7f2c"),
        "accent_text": HexColor("#fff6df"),
        "price": HexColor("#f3c65f"),
        "text": HexColor("#fff6df"),
        "muted": HexColor("#b8d3cb"),
        "line": HexColor("#2d6665"),
    },
    "burgundy-cream": {
        "background": HexColor("#3a0f1b"),
        "panel": HexColor("#571827"),
        "panel_dark": HexColor("#2a0911"),
        "accent": HexColor("#b7793d"),
        "accent_text": HexColor("#fff3de"),
        "price": HexColor("#f2d18b"),
        "text": HexColor("#fff3de"),
        "muted": HexColor("#d9b9a9"),
        "line": HexColor("#7b3847"),
    },
    "black-copper": {
        "background": HexColor("#151515"),
        "panel": HexColor("#24211f"),
        "panel_dark": HexColor("#0d0d0d"),
        "accent": HexColor("#b56332"),
        "accent_text": HexColor("#f7efe3"),
        "price": HexColor("#e2b66e"),
        "text": HexColor("#f7efe3"),
        "muted": HexColor("#bdb4a8"),
        "line": HexColor("#5b4a3e"),
    },
    "ivory-green": {
        "background": HexColor("#f2e7d2"),
        "panel": HexColor("#fff9ed"),
        "panel_dark": HexColor("#e8ddc5"),
        "accent": HexColor("#1c5c47"),
        "accent_text": HexColor("#fff9ed"),
        "price": HexColor("#b86a2e"),
        "text": HexColor("#173d32"),
        "muted": HexColor("#667c70"),
        "line": HexColor("#b9a88a"),
    },
}

BACKGROUND = PALETTES["teal-gold"]["background"]
PANEL = PALETTES["teal-gold"]["panel"]
PANEL_DARK = PALETTES["teal-gold"]["panel_dark"]
ORANGE = PALETTES["teal-gold"]["accent"]
ACCENT_TEXT = PALETTES["teal-gold"]["accent_text"]
GOLD = PALETTES["teal-gold"]["price"]
CREAM = PALETTES["teal-gold"]["text"]
MUTED = PALETTES["teal-gold"]["muted"]
LINE = PALETTES["teal-gold"]["line"]

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "frontend/src/assets/logo.png"
GENERATED_FOOD_ASSETS = {
    "qovirma lagmon": ROOT / "frontend/src/assets/menu/qovurma-lagmon-generated.png",
    "lag'mon": ROOT / "frontend/src/assets/menu/lagmon-generated.png",
    "olot somsa": ROOT / "frontend/src/assets/menu/olot-somsa-generated.png",
    "mastava": ROOT / "frontend/src/assets/menu/mastava-generated.png",
}


def _set_palette(name: str) -> None:
    colors = PALETTES[name]
    global BACKGROUND, PANEL, PANEL_DARK, ORANGE, ACCENT_TEXT, GOLD, CREAM, MUTED, LINE
    BACKGROUND = colors["background"]
    PANEL = colors["panel"]
    PANEL_DARK = colors["panel_dark"]
    ORANGE = colors["accent"]
    ACCENT_TEXT = colors["accent_text"]
    GOLD = colors["price"]
    CREAM = colors["text"]
    MUTED = colors["muted"]
    LINE = colors["line"]


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
    fill=None,
) -> None:
    pdf.setFillColor(PANEL if fill is None else fill)
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
    pdf.setFillColor(ACCENT_TEXT)
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
    source_override: Path | None = None,
) -> bool:
    downloaded = source_override or _download_image(item, cache_dir)
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


def select_featured_food_items(items: list[dict]) -> list[dict]:
    """Choose only main dishes with real AliPOS images for food photo cards."""
    catalog = {str(item.get("name", "")).casefold(): item for item in items}
    return [
        item
        for name in ("Qovirma lagmon", "Lag'mon", "1 kg Osh", "Mastava")
        if (item := catalog.get(name.casefold()))
        and (_generated_food_asset(item) or _image_url(item))
    ]


def _generated_food_asset(item: dict) -> Path | None:
    asset = GENERATED_FOOD_ASSETS.get(str(item.get("name", "")).casefold())
    return asset if asset and asset.exists() else None


def _draw_header(pdf: canvas.Canvas) -> None:
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

    title_left = margin + 300
    title_right = page_width - margin - 18
    title_center = (title_left + title_right) / 2
    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica-Bold", 96)
    pdf.drawCentredString(title_center, header_y + 174, "MENYU")
    badge_width = 350
    pdf.setFillColor(ORANGE)
    pdf.roundRect(
        title_center - badge_width / 2,
        header_y + 123,
        badge_width,
        35,
        11,
        stroke=0,
        fill=1,
    )
    pdf.setFillColor(ACCENT_TEXT)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(title_center, header_y + 135, "NARXLAR SO'MDA")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(title_center, header_y + 88, "OLOT SOMSA")


def _draw_food_panel(
    pdf: canvas.Canvas,
    items: list[dict],
    x: float,
    y: float,
    width: float,
    height: float,
    cache_dir: Path,
) -> None:
    _draw_panel(pdf, x, y, width, height)
    _draw_section_header(pdf, "OVQATLAR", x + 18, y + height - 18, width - 36)

    featured = select_featured_food_items(items)
    drawn_featured_ids: set[str] = set()
    drawn_featured_rows: set[int] = set()
    if featured:
        feature_gap = 18
        feature_width = (width - 36 - feature_gap) / 2
        photo_height = 112
        row_stride = 163
        photo_top = y + height - 84
        for index, item in enumerate(featured[:4]):
            row_index = index // 2
            column_index = index % 2
            feature_x = x + 18 + column_index * (feature_width + feature_gap)
            photo_y = photo_top - photo_height - row_index * row_stride
            if _draw_photo(
                pdf,
                item,
                feature_x,
                photo_y,
                feature_width,
                photo_height,
                cache_dir,
                caption=False,
                source_override=_generated_food_asset(item),
            ):
                _draw_item_row(
                    pdf,
                    item,
                    feature_x + 2,
                    photo_y - 27,
                    feature_width - 4,
                    name_size=15,
                    price_size=14,
                )
                drawn_featured_ids.add(str(item.get("id")))
                drawn_featured_rows.add(row_index)

    list_items = [
        item for item in items if str(item.get("id")) not in drawn_featured_ids
    ]
    split_at = (len(list_items) + 1) // 2
    columns = (list_items[:split_at], list_items[split_at:])
    inner_gap = 24
    inner_width = (width - 36 - inner_gap) / 2
    featured_row_count = max(drawn_featured_rows, default=-1) + 1
    start_offset = 126 + featured_row_count * 163 if featured_row_count else 101
    start_y = y + height - start_offset
    available_height = start_y - (y + 52)
    line_height = min(58, available_height / max(split_at - 1, 1))
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
            source_override=_generated_food_asset(items[0]),
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


def build_menu_pdf(
    menu: dict,
    output_path: Path,
    cache_dir: Path,
    *,
    palette_name: str = "teal-gold",
) -> None:
    """Render one A2 portrait page from AliPOS composition data."""
    _set_palette(palette_name)
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
    _draw_header(pdf)

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

    _draw_food_panel(
        pdf,
        food,
        margin,
        content_y,
        food_width,
        content_height,
        cache_dir,
    )
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
    cache_dir = ROOT / "tmp/pdfs/olot-somsa-a2/images"
    menu = asyncio.run(load_live_menu())
    for palette_name in PALETTES:
        output = ROOT / f"output/pdf/olot-somsa-menu-a2-{palette_name}.pdf"
        build_menu_pdf(menu, output, cache_dir, palette_name=palette_name)
        print(
            f"Rendered {len(menu.get('items', []))} items to "
            f"{output.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()
