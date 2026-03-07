from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from bookforge.layout.pdf import PDFLayoutEngine
from bookforge.review.book_sequence import build_book_sequence_report
from bookforge.story.storyweaver_parser import parse_storyweaver_markdown
from bookforge.typography import (
    extract_storyweaver_typography_directives,
    plan_page_typography,
    preserve_exact_printed_markdown,
    score_typography_plan,
)


def test_storyweaver_typography_directive_extraction_roles():
    md = "# GRRRRROWL\nThe *quiet* cave\n  hum  hum\nsleep"
    directives = extract_storyweaver_typography_directives(md, "typography spaced across the page")
    roles = {d.role for d in directives}
    assert "title_dramatic" in roles
    assert "emphasis" in roles
    assert "sound_effect" in roles
    assert "pause_gap" in roles
    assert "whisper" in roles


def test_exact_text_preservation():
    text = "# GRRRRROWL\nDo not rewrite *anything*."
    assert preserve_exact_printed_markdown(text) == text


def test_typography_plan_emphasis_whisper_sound_effect_and_bounds():
    plan = plan_page_typography(
        page_number=9,
        printed_markdown="# GRRRRROWL\n*soft*\nsleep",
        page_architecture_context={"text_zone": {"x": 0.1, "y": 0.07, "w": 0.8, "h": 0.2}},
        camera_context={"shot_type": "closeup_emotion"},
    )
    assert any(line.role == "title_dramatic" for line in plan.lines)
    assert any(line.role == "whisper" for line in plan.lines)
    assert any(line.role in {"sound_effect", "title_dramatic"} for line in plan.lines)
    assert 0.0 <= plan.quietness_requirement <= 1.0
    assert 0.0 <= plan.contrast_requirement <= 1.0


def test_typography_score_schema_and_sane_bounds():
    plan = plan_page_typography(page_number=1, printed_markdown="hello *there*")
    score = score_typography_plan(plan)
    payload = score.to_dict()
    for key in [
        "contrast_readability_score",
        "text_zone_quietness_score",
        "fit_score",
        "expressive_alignment_score",
        "readaloud_rhythm_score",
        "print_safety_score",
        "composite_score",
    ]:
        assert 0.0 <= float(payload[key]) <= 1.0


def test_renderer_consumes_typography_plan_and_fallback(tmp_path: Path):
    img = tmp_path / "img.png"
    Image.new("RGB", (600, 600), (220, 220, 220)).save(img)

    plan = plan_page_typography(page_number=1, printed_markdown="# ROAR\nsleep")
    engine = PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))
    out_pdf = tmp_path / "interior.pdf"
    result = engine.render_interior(
        pages=[{"page_number": 1, "text": "Hello", "typography_plan": plan.to_dict(), "typography_directives": []}],
        image_paths=[str(img)],
        output_interior=out_pdf,
        size="8.5x8.5",
        bleed_in=0.125,
        safe_margin_in=0.25,
        layout_preset={"panel_height_ratio": 0.22, "panel_position": "bottom", "panel_padding_pt": 12, "text_align": "center", "show_page_numbers": False},
        typography_preset={"base_font_size": 18, "min_font_size": 12, "leading": 1.25, "max_lines": 8},
    )
    row = result["applied_page_architecture"][0]
    assert row["typography_overlay_count"] >= 1
    assert row["typography_render_fallback"] is False


def test_overflow_hard_fail_still_applies(tmp_path: Path):
    img = tmp_path / "img.png"
    Image.new("RGB", (600, 600), (220, 220, 220)).save(img)

    engine = PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))
    long_text = " ".join(["overflow"] * 300)
    try:
        engine.render_interior(
            pages=[{"page_number": 1, "text": long_text}],
            image_paths=[str(img)],
            output_interior=tmp_path / "interior.pdf",
            size="8.5x8.5",
            bleed_in=0.125,
            safe_margin_in=0.25,
            layout_preset={"panel_height_ratio": 0.08, "panel_position": "bottom", "panel_padding_pt": 12, "text_align": "center", "show_page_numbers": False},
            typography_preset={"base_font_size": 18, "min_font_size": 12, "leading": 1.25, "max_lines": 8},
        )
    except RuntimeError as exc:
        assert "Text overflow could not be resolved" in str(exc)
    else:
        raise AssertionError("Expected overflow hard-fail")


def test_review_typography_artifact_schema_behavior():
    report = build_book_sequence_report(
        page_count=2,
        color_script={},
        architecture_plan=[],
        applied_arch_rows=[{"page": 1, "typography_render_fallback": True}, {"page": 2, "typography_render_fallback": False}],
        qa_attempts=[],
        premium_qc={},
        camera_sequence_plan={},
        typography_rows=[
            {"page": 1, "style_roles": ["title_dramatic"], "typography_score": {"composite_score": 0.9, "fit_score": 0.9, "contrast_readability_score": 0.9, "expressive_alignment_score": 0.7}, "render_fallback": True},
            {"page": 2, "style_roles": ["body"], "typography_score": {"composite_score": 0.5, "fit_score": 0.5, "contrast_readability_score": 0.5, "expressive_alignment_score": 0.4}, "render_fallback": False},
        ],
    )
    payload = report.to_dict()
    assert "typography_sequence" in payload
    assert "high_quality_pages" in payload["typography_sequence"]


def test_storyweaver_parser_preserves_printed_text_with_typography_metadata():
    bundle = parse_storyweaver_markdown(Path("examples/grumblebeast_storyweaver.md"))
    page = bundle.pages[18]
    assert "GRRRRROWL" in page.printed_markdown
    assert any(d.get("role") == "title_dramatic" for d in page.typography_directives)
