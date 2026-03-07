from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.color_script.lab import cie_de2000, srgb_to_lab
from bookforge.color_script.scoring import (
    ColorAdherenceScore,
    compute_color_composite_score,
    extract_image_color_profile,
    score_candidate_image_colors,
    score_color_adherence,
)
from bookforge.qc.image_qc import choose_best_variant


def _solid(path: Path, rgb: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> Path:
    Image.new("RGB", size, rgb).save(path)
    return path


def _qa_config() -> dict[str, float]:
    return {
        "min_sharpness": -1.0,
        "min_entropy": -1.0,
        "min_contrast": -1.0,
        "max_border_bar_score": 1.0,
        "max_text_likelihood": 1.0,
        "max_watermark_likelihood": 1.0,
        "max_logo_likelihood": 1.0,
        "max_border_artifact_score": 1.0,
        "max_face_like_regions": 99,
        "min_style_hist_similarity": 0.0,
        "max_page_to_page_hist_drift": 1.0,
        "max_focus_bleed_overlap": 1.0,
        "min_brightness_p05": 0.0,
        "max_brightness_p95": 255.0,
        "max_out_of_gamut_risk": 1.0,
    }


def test_lab_conversion_and_delta_e_sanity():
    red = srgb_to_lab((255, 0, 0))
    orange = srgb_to_lab((250, 80, 10))
    blue = srgb_to_lab((0, 0, 255))
    assert cie_de2000(red, orange) < cie_de2000(red, blue)


def test_extract_image_color_profile_on_solid_image(tmp_path: Path):
    image_path = _solid(tmp_path / "warm.png", (250, 190, 80))
    profile = extract_image_color_profile(image_path)
    assert 40 <= profile.measured_lightness <= 90
    assert profile.measured_chroma > 20
    assert len(profile.extracted_dominants) == 3


def test_palette_adherence_and_forbidden_detection(tmp_path: Path):
    warm = np.full((64, 64, 3), (245, 186, 84), dtype=np.uint8)
    cold = np.full((64, 64, 3), (40, 70, 220), dtype=np.uint8)
    combo = np.vstack([warm, cold])
    img = Image.fromarray(combo, mode="RGB")

    profile = extract_image_color_profile(img)
    page_spec = {
        "target_lightness": profile.measured_lightness,
        "target_chroma": profile.measured_chroma,
        "target_temperature": profile.measured_temperature,
        "target_contrast": profile.measured_contrast,
        "dominant_colors_lab": [list(srgb_to_lab((245, 186, 84)).as_tuple())],
        "forbidden_colors_lab": [list(srgb_to_lab((40, 70, 220)).as_tuple())],
    }
    master = {
        "dominant_colors_lab": [list(srgb_to_lab((245, 186, 84)).as_tuple())],
        "accent_colors_lab": [],
        "neutrals_lab": [],
    }
    adherence = score_color_adherence(profile, page_spec, master, image=img)
    assert 0.35 <= adherence.palette_adherence_pct <= 0.65
    assert adherence.forbidden_color_score < 0.5


def test_composite_scoring_stability():
    a = ColorAdherenceScore(0.7, 0.8, 0.6, 0.5, 0.9, 0.65, 0.8, 0.65)
    b = ColorAdherenceScore(0.7, 0.8, 0.6, 0.5, 0.9, 0.65, 0.8, 0.65)
    assert compute_color_composite_score(a) == compute_color_composite_score(b)


def test_scoring_on_synthetic_palette_images(tmp_path: Path):
    image_path = _solid(tmp_path / "palette_match.png", (230, 180, 95), size=(80, 80))
    page_spec = {
        "target_lightness": 75.0,
        "target_chroma": 45.0,
        "target_temperature": 0.3,
        "target_contrast": 0.0,
        "dominant_colors_lab": [list(srgb_to_lab((230, 180, 95)).as_tuple())],
        "forbidden_colors_lab": [list(srgb_to_lab((0, 0, 255)).as_tuple())],
    }
    master = {
        "dominant_colors_lab": [list(srgb_to_lab((230, 180, 95)).as_tuple())],
        "accent_colors_lab": [list(srgb_to_lab((200, 140, 60)).as_tuple())],
        "neutrals_lab": [list(srgb_to_lab((180, 170, 160)).as_tuple())],
    }
    result = score_candidate_image_colors(image_path, page_number=2, page_spec=page_spec, master_palette=master)
    assert result.page_number == 2
    assert result.composite_score > 0.6
    assert result.disposition in {"ACCEPT", "POST_PROCESS", "REJECT"}


def test_pipeline_candidate_metadata_attaches_color_score(tmp_path: Path):
    style = _solid(tmp_path / "style.png", (220, 180, 100))
    v1 = _solid(tmp_path / "v1.png", (220, 180, 100))
    v2 = _solid(tmp_path / "v2.png", (30, 30, 220))

    page_spec = {
        "target_lightness": 72.0,
        "target_chroma": 40.0,
        "target_temperature": 0.2,
        "target_contrast": 0.0,
        "dominant_colors_lab": [list(srgb_to_lab((220, 180, 100)).as_tuple())],
        "forbidden_colors_lab": [list(srgb_to_lab((30, 30, 220)).as_tuple())],
    }
    master = {
        "dominant_colors_lab": [list(srgb_to_lab((220, 180, 100)).as_tuple())],
        "accent_colors_lab": [list(srgb_to_lab((180, 130, 90)).as_tuple())],
        "neutrals_lab": [list(srgb_to_lab((160, 160, 160)).as_tuple())],
    }

    _best, qa = choose_best_variant([v1, v2], _qa_config(), style_ref=style, prev_ref=None, page_number=1, page_color_spec=page_spec, master_palette=master)
    assert "color_score" in qa["best"]["metadata"]
    assert qa["best"]["metadata"]["color_score"]["page_number"] == 1
