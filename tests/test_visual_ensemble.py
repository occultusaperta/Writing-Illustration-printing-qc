from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.qc.ensemble_visual import evaluate_visual_ensemble
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


def test_composition_score_sanity_on_off_thirds_focus(tmp_path: Path):
    focused = np.zeros((120, 120, 3), dtype=np.uint8)
    focused[38:58, 38:58] = 255
    centered = np.zeros((120, 120, 3), dtype=np.uint8)
    centered[52:72, 52:72] = 255

    f_path = tmp_path / "focus_thirds.png"
    c_path = tmp_path / "focus_center.png"
    Image.fromarray(focused, mode="RGB").save(f_path)
    Image.fromarray(centered, mode="RGB").save(c_path)

    thirds = evaluate_visual_ensemble(f_path)
    center = evaluate_visual_ensemble(c_path)
    assert thirds.composition_score > center.composition_score


def test_clarity_detects_blur_vs_sharp(tmp_path: Path):
    checker = (np.indices((128, 128)).sum(axis=0) % 2 * 255).astype(np.uint8)
    sharp = np.dstack([checker, checker, checker])
    blur = np.full_like(sharp, 127)

    sharp_path = tmp_path / "sharp.png"
    blur_path = tmp_path / "blur.png"
    Image.fromarray(sharp, mode="RGB").save(sharp_path)
    Image.fromarray(blur, mode="RGB").save(blur_path)

    sharp_score = evaluate_visual_ensemble(sharp_path)
    blur_score = evaluate_visual_ensemble(blur_path)
    assert sharp_score.clarity_score > blur_score.clarity_score


def test_artifact_detection_penalizes_banding_and_blocking(tmp_path: Path):
    clean = np.linspace(0, 255, 128, dtype=np.uint8)
    clean_img = np.tile(clean, (128, 1))

    bad = np.tile((np.arange(128) // 8) * 16, (128, 1)).astype(np.uint8)
    bad[:, 7::8] = 255

    clean_path = tmp_path / "clean.png"
    bad_path = tmp_path / "bad.png"
    Image.fromarray(np.dstack([clean_img] * 3), mode="RGB").save(clean_path)
    Image.fromarray(np.dstack([bad] * 3), mode="RGB").save(bad_path)

    clean_score = evaluate_visual_ensemble(clean_path)
    bad_score = evaluate_visual_ensemble(bad_path)
    assert clean_score.artifact_score > bad_score.artifact_score


def test_ensemble_score_bounds(tmp_path: Path):
    noise = np.random.default_rng(4).integers(0, 255, size=(96, 96, 3), dtype=np.uint8)
    path = tmp_path / "noise.png"
    Image.fromarray(noise, mode="RGB").save(path)

    result = evaluate_visual_ensemble(path)
    assert 0.0 <= result.ensemble_score <= 1.0


def test_pipeline_attaches_visual_ensemble_metadata(tmp_path: Path):
    style = tmp_path / "style.png"
    Image.new("RGB", (96, 96), (120, 100, 90)).save(style)

    v1 = tmp_path / "v1.png"
    v2 = tmp_path / "v2.png"
    Image.new("RGB", (96, 96), (130, 110, 100)).save(v1)
    Image.new("RGB", (96, 96), (80, 140, 180)).save(v2)

    _best, qa = choose_best_variant([v1, v2], _qa_config(), style_ref=style, prev_ref=None, page_number=1, page_color_spec={"target_lightness": 60.0, "target_chroma": 20.0, "target_temperature": 0.0, "target_contrast": 0.2}, master_palette={"dominant_colors_lab": [], "accent_colors_lab": [], "neutrals_lab": []})

    for variant in qa["variants"]:
        meta = variant.get("metadata", {})
        assert "visual_ensemble" in meta
        assert 0.0 <= meta["visual_ensemble"]["ensemble_score"] <= 1.0
