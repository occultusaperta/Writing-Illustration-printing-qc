from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.page_architecture.scoring import (
    ArchitectureVariantScoreResult,
    estimate_text_fitting,
    score_architecture_variant,
    score_focal_alignment,
    score_gutter_safety,
    score_text_readability,
)
from bookforge.page_architecture.templates import architecture_templates
from bookforge.pipeline import _load_architecture_scoring_context
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


def test_text_readability_prefers_quiet_text_zone():
    zones = [{"zone_id": "t", "zone_type": "text", "x": 0.0, "y": 0.0, "w": 0.5, "h": 1.0}]
    noisy = np.random.default_rng(42).integers(0, 255, size=(128, 128, 3), dtype=np.uint8).astype(np.float32)
    calm = np.full((128, 128, 3), 160.0, dtype=np.float32)

    noisy_score, _ = score_text_readability(zones, noisy, "full_bleed_single")
    calm_score, _ = score_text_readability(zones, calm, "full_bleed_single")
    assert calm_score > noisy_score


def test_focal_alignment_scores_higher_when_focus_in_art_zone():
    zones = [
        {"zone_id": "art", "zone_type": "art", "x": 0.6, "y": 0.0, "w": 0.4, "h": 1.0},
        {"zone_id": "text", "zone_type": "text", "x": 0.0, "y": 0.0, "w": 0.4, "h": 1.0},
    ]
    right_focus = np.zeros((100, 100, 3), dtype=np.float32)
    right_focus[:, 85:95, :] = 255.0
    left_focus = np.zeros((100, 100, 3), dtype=np.float32)
    left_focus[:, 5:15, :] = 255.0

    score_art, _ = score_focal_alignment(zones, right_focus)
    score_text, _ = score_focal_alignment(zones, left_focus)
    assert score_art > score_text


def test_text_fitting_penalizes_overflow():
    zones = [{"zone_id": "text", "zone_type": "text", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1}]
    long_text = " ".join(["storybook"] * 120)
    short_text = "tiny line"
    long_score, _ = estimate_text_fitting(long_text, zones, age_range="3-5")
    short_score, _ = estimate_text_fitting(short_text, zones, age_range="3-5")
    assert short_score > long_score


def test_gutter_safety_detects_center_risk():
    zones = [{"zone_id": "art", "zone_type": "art", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]
    center_busy = np.zeros((120, 120, 3), dtype=np.float32)
    center_busy[:, 55:65, :] = 255.0
    side_busy = np.zeros((120, 120, 3), dtype=np.float32)
    side_busy[:, 5:15, :] = 255.0

    center_score, _ = score_gutter_safety(zones, center_busy)
    side_score, _ = score_gutter_safety(zones, side_busy)
    assert side_score > center_score


def test_architecture_score_result_schema(tmp_path: Path):
    img = tmp_path / "page.png"
    Image.new("RGB", (160, 160), (140, 170, 180)).save(img)
    variant = next(v for v in architecture_templates() if v.variant_id == "full_bleed_single_caption")

    result = score_architecture_variant(variant, page_text="A short line.", image=img, age_range="5-7")
    assert isinstance(result, ArchitectureVariantScoreResult)
    payload = result.to_dict()
    assert payload["variant_id"] == "full_bleed_single_caption"
    assert 0.0 <= payload["composite_score"] <= 1.0
    assert "diagnostics" in payload and "notes" in payload["diagnostics"]


def test_pipeline_metadata_attachment_with_and_without_architecture(tmp_path: Path):
    style = tmp_path / "style.png"
    Image.new("RGB", (96, 96), (120, 120, 120)).save(style)
    v1 = tmp_path / "v1.png"
    v2 = tmp_path / "v2.png"
    Image.new("RGB", (96, 96), (100, 130, 150)).save(v1)
    Image.new("RGB", (96, 96), (160, 120, 90)).save(v2)

    arch = {
        "variant_id": "full_bleed_single_caption",
        "architecture_type": "full_bleed_single",
        "zones": [
            {"zone_id": "art", "zone_type": "art", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            {"zone_id": "text", "zone_type": "text", "x": 0.08, "y": 0.78, "w": 0.84, "h": 0.14},
        ],
    }

    _best, qa_with_arch = choose_best_variant(
        [v1, v2],
        _qa_config(),
        style_ref=style,
        prev_ref=None,
        page_number=1,
        page_text="A simple sentence for testing.",
        architecture_variant=arch,
        age_range="5-7",
    )
    assert "page_architecture_score" in qa_with_arch["variants"][0]["metadata"]

    _best2, qa_no_arch = choose_best_variant([v1, v2], _qa_config(), style_ref=style, prev_ref=None, page_number=1, page_text="A simple sentence")
    assert "page_architecture_score" not in qa_no_arch["variants"][0].get("metadata", {})


def test_architecture_scoring_context_loader_handles_missing_and_present_artifacts(tmp_path: Path):
    assert _load_architecture_scoring_context(tmp_path) == {}

    planning = tmp_path / "preprod" / "planning"
    planning.mkdir(parents=True)
    (planning / "architecture_plan.json").write_text(
        '[{"page_number": 1, "selected_variant_id": "full_bleed_single_caption"}]', encoding="utf-8"
    )
    loaded = _load_architecture_scoring_context(tmp_path)
    assert 1 in loaded
    assert loaded[1]["variant_id"] == "full_bleed_single_caption"
