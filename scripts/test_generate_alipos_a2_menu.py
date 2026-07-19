from pathlib import Path

from pypdf import PdfReader

import generate_alipos_a2_menu as renderer


def test_renderer_module_exists():
    assert Path(__file__).with_name("generate_alipos_a2_menu.py").is_file()


def test_format_price_groups_uzs_thousands():
    assert renderer.format_price(35000.0) == "35 000"
    assert renderer.format_price("4000") == "4 000"


def test_normalize_display_name_changes_only_presentation():
    assert renderer.normalize_display_name("qora choy") == "Qora choy"
    assert renderer.normalize_display_name("cola 1,L") == "Cola 1 L"


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

    grouped = renderer.group_items(menu)

    assert [item["id"] for items in grouped.values() for item in items] == ["1", "2"]


def test_build_menu_pdf_is_one_a2_portrait_page(tmp_path: Path):
    menu = {
        "categories": [{"id": "food", "name": "ovqat"}],
        "items": [
            {"id": "1", "categoryId": "food", "name": "Osh", "price": 30000}
        ],
    }
    output = tmp_path / "menu.pdf"

    renderer.build_menu_pdf(menu, output, tmp_path / "images")

    reader = PdfReader(str(output))
    page = reader.pages[0]
    assert len(reader.pages) == 1
    assert abs(float(page.mediabox.width) - 1190.55) < 0.6
    assert abs(float(page.mediabox.height) - 1683.78) < 0.6


def test_build_menu_pdf_uses_customer_facing_header_copy(tmp_path: Path):
    menu = {
        "categories": [{"id": "food", "name": "ovqat"}],
        "items": [
            {"id": "1", "categoryId": "food", "name": "Osh", "price": 30000}
        ],
    }
    output = tmp_path / "menu.pdf"

    renderer.build_menu_pdf(menu, output, tmp_path / "images")

    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)
    assert "OLOT SOMSA" in text
    assert "AliPOSdagi" not in text


def test_featured_food_photos_exclude_sauces_and_small_items():
    items = [
        {"id": "qovurma", "name": "Qovirma lagmon", "images": []},
        {"id": "lagmon", "name": "Lag'mon", "images": []},
        {
            "id": "osh",
            "name": "1 kg Osh",
            "images": [{"url": "https://example.test/osh.jpg"}],
        },
        {
            "id": "mastava",
            "name": "Mastava",
            "images": [{"url": "https://example.test/mastava.jpg"}],
        },
        {
            "id": "sous",
            "name": "Sous",
            "images": [{"url": "https://example.test/sous.jpg"}],
        },
        {
            "id": "qatiq",
            "name": "Qatiq kichik",
            "images": [{"url": "https://example.test/qatiq.jpg"}],
        },
    ]

    selected = renderer.select_featured_food_items(items)

    assert [item["id"] for item in selected] == [
        "qovurma",
        "lagmon",
        "osh",
        "mastava",
    ]


def test_four_named_color_variants_are_available():
    assert list(renderer.PALETTES) == [
        "teal-gold",
        "burgundy-cream",
        "black-copper",
        "ivory-green",
    ]


def test_panel_default_uses_the_active_palette_color():
    class RecordingCanvas:
        def __init__(self):
            self.fill_colors = []

        def setFillColor(self, color):
            self.fill_colors.append(color)

        def setStrokeColor(self, _color):
            pass

        def setLineWidth(self, _width):
            pass

        def roundRect(self, *_args, **_kwargs):
            pass

    pdf = RecordingCanvas()
    renderer._set_palette("ivory-green")
    try:
        renderer._draw_panel(pdf, 0, 0, 100, 100)
    finally:
        renderer._set_palette("teal-gold")

    assert pdf.fill_colors[0] == renderer.PALETTES["ivory-green"]["panel"]


def test_ivory_section_header_uses_light_text_on_green():
    class RecordingCanvas:
        def __init__(self):
            self.fill_colors = []

        def setFillColor(self, color):
            self.fill_colors.append(color)

        def roundRect(self, *_args, **_kwargs):
            pass

        def setFont(self, *_args, **_kwargs):
            pass

        def drawString(self, *_args, **_kwargs):
            pass

    pdf = RecordingCanvas()
    renderer._set_palette("ivory-green")
    try:
        renderer._draw_section_header(pdf, "OVQATLAR", 0, 100, 200)
    finally:
        renderer._set_palette("teal-gold")

    assert pdf.fill_colors[1] == renderer.HexColor("#fff9ed")
