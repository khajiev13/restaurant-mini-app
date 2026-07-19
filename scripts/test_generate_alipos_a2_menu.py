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
