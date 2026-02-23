import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from bookforge.illustration.color_grade import add_sharpen_and_grain, grade_image
from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout.pdf import PDFLayoutEngine, fit_cover_image_to_rect
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.composition_qc import focus_bleed_overlap


def test_cache_key_changes_when_reference_changes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "x")
    ill = FalFluxIllustrator(endpoint="https://fal.run/fal-ai/flux/schnell")

    r1 = tmp_path / "r1.png"
    r2 = tmp_path / "r2.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(r1)
    Image.new("RGB", (8, 8), (0, 0, 255)).save(r2)

    key1 = ill._build_cache_key("p", 7, (100, 100), 6, None, r1)
    key2 = ill._build_cache_key("p", 7, (100, 100), 6, None, r2)
    assert key1 != key2


def test_cache_key_changes_when_steps_changes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "x")
    ill = FalFluxIllustrator()
    r = tmp_path / "r.png"
    Image.new("RGB", (8, 8), (12, 34, 56)).save(r)
    key1 = ill._build_cache_key("p", 7, (100, 100), 4, None, r)
    key2 = ill._build_cache_key("p", 7, (100, 100), 8, None, r)
    assert key1 != key2


def test_color_grade_moves_hist_toward_style(tmp_path: Path):
    src = tmp_path / "src.png"
    style = tmp_path / "style.png"
    Image.new("RGB", (80, 80), (40, 80, 190)).save(src)
    Image.new("RGB", (80, 80), (180, 140, 60)).save(style)

    out = grade_image(src, style, ["#A05040"], mode="match_style", strength=0.5)
    src_mean = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32).mean(axis=(0, 1))
    style_mean = np.asarray(Image.open(style).convert("RGB"), dtype=np.float32).mean(axis=(0, 1))
    out_mean = np.asarray(out, dtype=np.float32).mean(axis=(0, 1))
    assert np.linalg.norm(out_mean - style_mean) < np.linalg.norm(src_mean - style_mean)


def test_grain_does_not_change_dimensions():
    img = Image.new("RGB", (123, 87), (100, 110, 120))
    out = add_sharpen_and_grain(img, sharpen_amount=0.2, grain_amount=0.2)
    assert out.size == img.size


def test_postprocess_is_deterministic_given_same_inputs(tmp_path: Path):
    src = tmp_path / "src.png"
    style = tmp_path / "style.png"
    Image.new("RGB", (64, 64), (90, 120, 170)).save(src)
    Image.new("RGB", (64, 64), (130, 90, 60)).save(style)
    a = np.asarray(add_sharpen_and_grain(grade_image(src, style, ["#A07050"], "match_style_plus_palette", 0.35), 0.15, 0.05))
    b = np.asarray(add_sharpen_and_grain(grade_image(src, style, ["#A07050"], "match_style_plus_palette", 0.35), 0.15, 0.05))
    assert np.array_equal(a, b)


def test_focus_bleed_overlap_detects_edge_heavy_image(tmp_path: Path):
    edge = tmp_path / "edge.png"
    img = Image.new("RGB", (200, 200), (120, 120, 120))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 30, 199), fill=(0, 0, 0))
    img.save(edge)
    report = focus_bleed_overlap(edge)
    assert report["overlap"] > 0.15


def test_cover_fit_produces_exact_aspect(tmp_path: Path):
    src = tmp_path / "cover.png"
    Image.new("RGB", (300, 100), (20, 40, 60)).save(src)
    fitted = fit_cover_image_to_rect(src, 240, 400)
    with Image.open(fitted) as im:
        assert im.size == (240, 400)


def test_pdf_compression_flag_set():
    src = Path("bookforge/layout/pdf.py").read_text(encoding="utf-8")
    assert "pageCompression=1" in src


def test_jpeg_temp_conversion_keeps_dimensions(tmp_path: Path):
    engine = PDFLayoutEngine.__new__(PDFLayoutEngine)
    engine.font_name = "Helvetica"
    page = tmp_path / "p.png"
    Image.new("RGB", (600, 600), (100, 140, 180)).save(page)
    out = tmp_path / "interior.pdf"
    engine.render_interior(
        [{"page_number": 1, "text": "Hello"}],
        [str(page)],
        out,
        "8.5x8.5",
        0.125,
        0.375,
        {"panel_height_ratio": 0.25, "panel_position": "bottom", "panel_padding_pt": 14, "text_align": "center", "show_page_numbers": True},
        {"base_font_size": 16, "min_font_size": 11, "leading": 1.2, "max_lines": 8},
        {"image_embed": "jpeg", "jpeg_quality": 90},
    )
    assert out.exists() and out.stat().st_size > 0


def test_quality_summary_written_with_sections(tmp_path: Path):
    lock = {"qa": {"max_text_likelihood": 0.2, "max_watermark_likelihood": 0.2, "max_logo_likelihood": 0.2}}
    qa_attempts = [
        {"page": 1, "attempt": 1, "best": {"sharpness": 1, "contrast": 1, "entropy": 1, "text_likelihood": 0.0, "watermark_likelihood": 0.0, "logo_likelihood": 0.0}},
        {"page": 2, "attempt": 2, "best": {"sharpness": 0, "contrast": 0, "entropy": 0, "text_likelihood": 0.5, "watermark_likelihood": 0.0, "logo_likelihood": 0.0}},
    ]
    p = BookforgePipeline()._write_quality_summary(tmp_path, qa_attempts, {1: [True], 2: [False]}, lock)
    text = p.read_text(encoding="utf-8")
    assert "Top 5 Worst Pages" in text
    assert "Pages Regenerated" in text
    assert "Pages with Integrity Warnings" in text
    assert "Cache Hit Rate" in text
