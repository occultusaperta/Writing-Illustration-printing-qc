from pathlib import Path

from PIL import Image

from bookforge.layout.pdf import PDFLayoutEngine
from bookforge.page_architecture.layout_apply import build_layout_application_map
from bookforge.page_architecture.templates import architecture_templates
from bookforge.page_architecture.types import to_primitive


def _variants():
    return {v.variant_id: to_primitive(v) for v in architecture_templates()}


def _plan(page: int, variant_id: str, arch: str):
    return {"page_number": page, "selected_variant_id": variant_id, "selected_architecture_type": arch}


def test_full_bleed_spread_application_and_gutter_flag():
    pages = [{"page_number": 2, "text": "x"}, {"page_number": 3, "text": "y"}]
    applied = build_layout_application_map(
        pages,
        [_plan(2, "full_bleed_spread_main", "full_bleed_spread")],
        _variants(),
        spread_pairs=[(2, 3)],
    )
    assert applied[2]["compositor_hints"]["mode"] == "full_bleed_spread"
    assert applied[2]["gutter_safe_applied"] is True


def test_full_bleed_single_left_right_behavior():
    pages = [{"page_number": 1, "text": "left"}, {"page_number": 2, "text": "right"}]
    plan = [
        _plan(1, "full_bleed_single_caption", "full_bleed_single"),
        _plan(2, "full_bleed_single_caption", "full_bleed_single"),
    ]
    applied = build_layout_application_map(pages, plan, _variants(), spread_pairs=[])
    assert applied[1]["suppress_body_text"] is True
    assert applied[1]["compositor_hints"]["mode"] == "full_bleed_single_art_page"
    assert applied[2]["suppress_body_text"] is False
    assert applied[2]["compositor_hints"]["mode"] == "full_bleed_single_text_page"


def test_vignette_text_dominant_wordless_and_inset_modes():
    pages = [
        {"page_number": 1, "text": "v"},
        {"page_number": 2, "text": "t"},
        {"page_number": 3, "text": "w"},
        {"page_number": 4, "text": "i"},
    ]
    plan = [
        _plan(1, "vignette_centered", "vignette"),
        _plan(2, "text_dominant_story", "text_dominant"),
        _plan(3, "wordless_spread_hero", "wordless_spread"),
        _plan(4, "inset_composite_stack", "inset_composite"),
    ]
    applied = build_layout_application_map(pages, plan, _variants(), spread_pairs=[(3, 4)])
    assert applied[1]["compositor_hints"]["mode"] == "vignette"
    assert applied[1]["reserve_whitespace"]
    assert applied[2]["compositor_hints"]["mode"] == "text_dominant"
    assert applied[3]["suppress_body_text"] is True
    assert applied[4]["compositor_hints"]["mode"] == "inset_composite"
    assert len(applied[4]["inset_zones"]) >= 1


def test_safe_fallback_when_architecture_missing():
    pages = [{"page_number": 1, "text": "a"}]
    applied = build_layout_application_map(pages, None, _variants(), spread_pairs=[])
    assert applied[1]["compositor_hints"]["mode"] == "legacy_default"
    assert applied[1]["layout_fallback_reason"] == "architecture_plan_missing"


def test_pdf_render_returns_applied_architecture_metadata(tmp_path: Path):
    engine = PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))
    p1 = tmp_path / "1.png"
    p2 = tmp_path / "2.png"
    Image.new("RGB", (640, 640), (100, 140, 180)).save(p1)
    Image.new("RGB", (640, 640), (120, 100, 180)).save(p2)
    pages = [{"page_number": 1, "text": ""}, {"page_number": 2, "text": "Lots of text here for layout."}]
    applied = {
        1: {
            "architecture_type": "wordless_spread",
            "variant_id": "wordless_spread_hero",
            "compositor_hints": {"mode": "wordless_spread"},
            "suppress_body_text": True,
            "gutter_safe_applied": True,
            "layout_fallback_reason": "",
        },
        2: {
            "architecture_type": "text_dominant",
            "variant_id": "text_dominant_story",
            "text_zone": {"x": 0.08, "y": 0.08, "w": 0.84, "h": 0.40},
            "compositor_hints": {"mode": "text_dominant"},
            "suppress_body_text": False,
            "gutter_safe_applied": False,
            "layout_fallback_reason": "",
        },
    }
    out_pdf = tmp_path / "interior.pdf"
    meta = engine.render_interior(
        pages,
        [str(p1), str(p2)],
        out_pdf,
        "8.5x8.5",
        0.125,
        0.375,
        {"panel_height_ratio": 0.25, "panel_position": "bottom", "panel_padding_pt": 14, "text_align": "center", "show_page_numbers": True},
        {"base_font_size": 16, "min_font_size": 11, "leading": 1.2, "max_lines": 8},
        {"image_embed": "jpeg", "jpeg_quality": 90},
        architecture_layout=applied,
    )
    assert out_pdf.exists() and out_pdf.stat().st_size > 0
    assert "applied_page_architecture" in meta
    rows = {r["page"]: r for r in meta["applied_page_architecture"]}
    assert rows[1]["suppress_body_text"] is True
    assert rows[2]["layout_mode"] == "text_dominant"
