from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from bookforge.illustration.director_grade import apply_director_grade
from bookforge.illustration.smart_crop import smart_crop_to_target
from bookforge.layout.pdf import PDFLayoutEngine
from bookforge.review.html_report import generate_report
from bookforge.qc.print_qc import analyze_print_qc


def test_smart_crop_shifts_toward_focus(tmp_path: Path):
    img = Image.new("RGB", (400, 200), (128, 128, 128))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 90, 199), fill=(0, 0, 0))
    out = smart_crop_to_target(img, 200, 200)
    arr = np.asarray(out.convert("L"), dtype=np.float32)
    left_mean = arr[:, :40].mean()
    right_mean = arr[:, -40:].mean()
    assert left_mean < right_mean


def test_smart_crop_deterministic():
    img = Image.new("RGB", (350, 220), (100, 120, 140))
    a = np.asarray(smart_crop_to_target(img, 200, 200))
    b = np.asarray(smart_crop_to_target(img, 200, 200))
    assert np.array_equal(a, b)


def test_crop_preserves_exact_dimensions():
    img = Image.new("RGB", (500, 260), (10, 20, 30))
    out = smart_crop_to_target(img, 300, 200)
    assert out.size == (300, 200)


def test_director_grade_deterministic_with_seed():
    img = Image.new("RGB", (128, 96), (120, 140, 160))
    a = np.asarray(apply_director_grade(img, base_seed=77, page_no=2))
    b = np.asarray(apply_director_grade(img, base_seed=77, page_no=2))
    assert np.array_equal(a, b)


def test_paper_texture_changes_pixels_but_not_dims():
    img = Image.new("RGB", (111, 77), (120, 140, 160))
    out = apply_director_grade(img, base_seed=1, page_no=1, paper_texture_strength=0.1)
    assert out.size == img.size
    assert not np.array_equal(np.asarray(out), np.asarray(img))


def test_tone_curve_moves_histogram():
    img = Image.new("RGB", (100, 100), (90, 110, 130))
    out = apply_director_grade(img, base_seed=3, page_no=1, tone_curve_strength=0.7)
    assert abs(np.asarray(out, dtype=np.float32).mean() - np.asarray(img, dtype=np.float32).mean()) > 0.5


def test_print_qc_detects_dark_image(tmp_path: Path):
    p = tmp_path / "dark.png"
    Image.new("RGB", (90, 90), (10, 10, 10)).save(p)
    metrics = analyze_print_qc(p)
    assert metrics["brightness_p95"] < 80


def test_gamut_risk_heuristic_triggers_on_saturated_blocks(tmp_path: Path):
    p = tmp_path / "sat.png"
    img = Image.new("RGB", (100, 100), (255, 0, 255))
    img.save(p)
    metrics = analyze_print_qc(p)
    assert metrics["out_of_gamut_risk"] > 0.35


def test_cover_title_auto_chooses_less_busy_region(tmp_path: Path):
    cover = tmp_path / "cover.png"
    img = Image.new("RGB", (1000, 1000), (180, 180, 180))
    d = ImageDraw.Draw(img)
    for y in range(0, 200, 4):
        d.line((0, y, 999, y), fill=(0, 0, 0), width=2)
    img.save(cover)

    engine = PDFLayoutEngine.__new__(PDFLayoutEngine)
    top = engine._region_busyness(cover, (0, 0, 1000, 220))
    middle = engine._region_busyness(cover, (0, 380, 1000, 620))
    assert top > middle


def test_html_report_written_contains_sections(tmp_path: Path):
    out = tmp_path
    (out / "images").mkdir(parents=True, exist_ok=True)
    pages = []
    for i in range(2):
        p = out / "images" / f"page_{i+1:03d}.png"
        Image.new("RGB", (300, 300), (120 + i, 100, 140)).save(p)
        pages.append(p)
    cover = out / "cover_wrap.pdf"
    Image.new("RGB", (300, 300), (10, 20, 30)).save(out / "cover.png")
    qa = {"attempts": [{"page": 1, "best": {"path": str(pages[0]), "sharpness": 1, "text_likelihood": 0, "style_hist_similarity": 0.8, "page_to_page_hist_drift": 0.1, "brightness_mean": 120}}]}
    pr = {"drift": {"top_pages": [1]}, "regen_counts": {"1": 1}, "cache_hit_rate": 0.5}
    report = generate_report(out, pages, qa, pr, out / "cover.png")
    text = report.read_text(encoding="utf-8")
    assert "BookForge Static Proof Dashboard" in text
    assert "QA Table" in text


def test_thumbnails_created_count_matches_pages(tmp_path: Path):
    out = tmp_path
    (out / "images").mkdir(parents=True, exist_ok=True)
    pages = []
    for i in range(3):
        p = out / "images" / f"page_{i+1:03d}.png"
        Image.new("RGB", (200, 200), (30 + i, 40, 50)).save(p)
        pages.append(p)
    cover = out / "cover.png"
    Image.new("RGB", (200, 200), (60, 70, 80)).save(cover)
    generate_report(out, pages, {"attempts": []}, {"drift": {"top_pages": []}, "regen_counts": {}, "cache_hit_rate": 0.0}, cover)
    thumbs = list((out / "review" / "thumbs").glob("*.jpg"))
    assert len(thumbs) == 4
