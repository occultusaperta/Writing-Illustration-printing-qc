from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.color_script.postprocess import apply_color_postprocess
from bookforge.color_script.scoring import (
    ColorScoreResult,
    extract_image_color_profile,
    score_candidate_image_colors,
)
from bookforge.qc.image_qc import choose_best_variant


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


def _color_score_with_actions(path: Path, page_spec: dict, master: dict, actions: list[str]) -> ColorScoreResult:
    base = score_candidate_image_colors(path, page_number=1, page_spec=page_spec, master_palette=master)
    return ColorScoreResult(
        page_number=base.page_number,
        lightness_score=base.lightness_score,
        chroma_score=base.chroma_score,
        temperature_score=base.temperature_score,
        contrast_score=base.contrast_score,
        dominant_match_score=base.dominant_match_score,
        palette_adherence_score=base.palette_adherence_score,
        forbidden_color_score=base.forbidden_color_score,
        composite_score=base.composite_score,
        extracted_dominants=base.extracted_dominants,
        measured_lightness=base.measured_lightness,
        measured_chroma=base.measured_chroma,
        measured_temperature=base.measured_temperature,
        measured_contrast=base.measured_contrast,
        palette_adherence_pct=base.palette_adherence_pct,
        disposition=base.disposition,
        post_process_actions=actions,
    )


def test_lightness_correction_improves_score(tmp_path: Path):
    arr = np.full((80, 80, 3), 45, dtype=np.uint8)
    path = tmp_path / "dark.png"
    Image.fromarray(arr, mode="RGB").save(path)

    page_spec = {"target_lightness": 68.0, "target_chroma": 10.0, "target_temperature": 0.0, "target_contrast": 0.0}
    master = {"dominant_colors_lab": [], "accent_colors_lab": [], "neutrals_lab": []}
    score = _color_score_with_actions(path, page_spec, master, ["lightness_shift"])

    result = apply_color_postprocess(path, score, {**page_spec, "_master_palette": master})
    assert "lightness_shift" in result.actions_applied
    assert result.delta_scores_estimate["composite_delta"] >= 0.0


def test_contrast_lift_improves_contrast_metric(tmp_path: Path):
    grad = np.tile(np.linspace(110, 135, 120, dtype=np.uint8), (120, 1))
    rgb = np.dstack([grad, grad, grad])
    path = tmp_path / "low_contrast.png"
    Image.fromarray(rgb, mode="RGB").save(path)

    page_spec = {"target_lightness": 55.0, "target_chroma": 4.0, "target_temperature": 0.0, "target_contrast": 0.35}
    master = {"dominant_colors_lab": [], "accent_colors_lab": [], "neutrals_lab": []}
    score = _color_score_with_actions(path, page_spec, master, ["contrast_lift"])

    before = extract_image_color_profile(path).measured_contrast
    result = apply_color_postprocess(path, score, {**page_spec, "_master_palette": master})
    after = extract_image_color_profile(result.corrected_image).measured_contrast
    assert after >= before


def test_temperature_shift_adjusts_measured_temperature(tmp_path: Path):
    arr = np.full((90, 90, 3), (90, 120, 190), dtype=np.uint8)
    path = tmp_path / "cool.png"
    Image.fromarray(arr, mode="RGB").save(path)

    page_spec = {"target_lightness": 60.0, "target_chroma": 35.0, "target_temperature": 0.45, "target_contrast": 0.0}
    master = {"dominant_colors_lab": [], "accent_colors_lab": [], "neutrals_lab": []}
    score = _color_score_with_actions(path, page_spec, master, ["temperature_shift"])

    before = extract_image_color_profile(path).measured_temperature
    result = apply_color_postprocess(path, score, {**page_spec, "_master_palette": master})
    after = extract_image_color_profile(result.corrected_image).measured_temperature
    assert after > before


def test_composite_score_improves_after_correction(tmp_path: Path):
    arr = np.full((64, 64, 3), 38, dtype=np.uint8)
    path = tmp_path / "very_dark.png"
    Image.fromarray(arr, mode="RGB").save(path)

    page_spec = {
        "target_lightness": 70.0,
        "target_chroma": 12.0,
        "target_temperature": 0.0,
        "target_contrast": 0.25,
        "dominant_colors_lab": [],
        "forbidden_colors_lab": [],
    }
    master = {"dominant_colors_lab": [], "accent_colors_lab": [], "neutrals_lab": []}
    score = _color_score_with_actions(path, page_spec, master, ["lightness_shift", "contrast_lift"])

    result = apply_color_postprocess(path, score, {**page_spec, "_master_palette": master})
    assert result.delta_scores_estimate["new_composite"] >= result.delta_scores_estimate["original_composite"]


def test_pipeline_attaches_corrected_variant_metadata(tmp_path: Path):
    style = tmp_path / "style.png"
    Image.new("RGB", (64, 64), (180, 160, 120)).save(style)

    low_contrast = np.tile(np.linspace(120, 134, 96, dtype=np.uint8), (96, 1))
    v1 = tmp_path / "v1.png"
    Image.fromarray(np.dstack([low_contrast, low_contrast, low_contrast]), mode="RGB").save(v1)
    v2 = tmp_path / "v2.png"
    Image.new("RGB", (96, 96), (170, 130, 90)).save(v2)

    profile = extract_image_color_profile(v1)
    page_spec = {
        "target_lightness": profile.measured_lightness + 8.0,
        "target_chroma": profile.measured_chroma + 8.0,
        "target_temperature": profile.measured_temperature + 0.4,
        "target_contrast": 0.4,
        "dominant_colors_lab": [profile.extracted_dominants[0]],
        "forbidden_colors_lab": [],
    }
    master = {"dominant_colors_lab": [profile.extracted_dominants[0]], "accent_colors_lab": [], "neutrals_lab": []}

    _best, qa = choose_best_variant([v1, v2], _qa_config(), style_ref=style, prev_ref=None, page_number=3, page_color_spec=page_spec, master_palette=master)

    found = [v for v in qa["variants"] if "corrected_variant" in v.get("metadata", {})]
    assert found
    assert "color_postprocess" in found[0]["metadata"]
    assert "postprocess_score_delta" in found[0]["metadata"]["corrected_variant"]
