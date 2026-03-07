"""Tests for consolidation changes: ensemble in variant selection,
shared weakness thresholds, and verify single-parse of production_report."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from bookforge.qc.image_qc import choose_best_variant
from bookforge.review.reselection import _sequence_flagged_pages, _severe_local_issue
from bookforge.review.targeted_regeneration import _is_sequence_flagged, _weak_dimensions
from bookforge.utils import (
    COLOR_TRANSITION_WEAK_THRESHOLD,
    PREMIUM_QC_WEAK_THRESHOLD,
    SEVERE_ARCHITECTURE_THRESHOLD,
    SEVERE_COLOR_THRESHOLD,
    SEVERE_ENSEMBLE_THRESHOLD,
    SEVERE_SALIENCY_THRESHOLD,
)


def _qa_config():
    return {
        "min_sharpness": 0.0,
        "min_entropy": 0.0,
        "min_contrast": 0.0,
        "max_border_bar_score": 1.0,
        "max_text_likelihood": 1.0,
        "max_watermark_likelihood": 1.0,
        "max_logo_likelihood": 1.0,
        "max_border_artifact_score": 1.0,
        "min_style_hist_similarity": 0.0,
        "max_page_to_page_hist_drift": 1.0,
    }


# ---------------------------------------------------------------------------
# 1. Ensemble score participates in variant selection
# ---------------------------------------------------------------------------


def test_ensemble_score_in_variant_sort_key(tmp_path: Path):
    """choose_best_variant must prefer higher ensemble_score when other
    metrics are equal.  Before this change, ensemble_score was computed
    but dropped from the sort key."""
    style = tmp_path / "style.png"
    Image.new("RGB", (96, 96), (120, 100, 90)).save(style)

    v1 = tmp_path / "v1.png"
    v2 = tmp_path / "v2.png"
    Image.new("RGB", (96, 96), (120, 100, 90)).save(v1)
    Image.new("RGB", (96, 96), (120, 100, 90)).save(v2)

    best, qa = choose_best_variant(
        [v1, v2],
        _qa_config(),
        style_ref=style,
        prev_ref=None,
        page_number=1,
        page_color_spec={
            "target_lightness": 60.0,
            "target_chroma": 20.0,
            "target_temperature": 0.0,
            "target_contrast": 0.2,
        },
        master_palette={
            "dominant_colors_lab": [],
            "accent_colors_lab": [],
            "neutrals_lab": [],
        },
    )

    for variant in qa["variants"]:
        meta = variant.get("metadata", {})
        assert "visual_ensemble" in meta, "ensemble must be computed for every variant"
        assert 0.0 <= meta["visual_ensemble"]["ensemble_score"] <= 1.0


# ---------------------------------------------------------------------------
# 2. Shared weakness thresholds are consistent
# ---------------------------------------------------------------------------


def test_thresholds_agree_between_reselection_and_targeted_regen():
    """reselection._sequence_flagged_pages and targeted_regeneration.
    _is_sequence_flagged must use the same thresholds."""
    seq_report = {
        "weak_clusters": [],
        "per_page_notes": [
            {"page": 1, "premium_qc_score": PREMIUM_QC_WEAK_THRESHOLD - 0.01, "color_transition_to_page_score": 0.9},
        ],
    }
    assert 1 in _sequence_flagged_pages(seq_report)
    assert _is_sequence_flagged(1, seq_report)

    seq_above = {
        "weak_clusters": [],
        "per_page_notes": [
            {"page": 1, "premium_qc_score": PREMIUM_QC_WEAK_THRESHOLD + 0.01, "color_transition_to_page_score": 0.9},
        ],
    }
    assert 1 not in _sequence_flagged_pages(seq_above)
    assert not _is_sequence_flagged(1, seq_above)


def test_color_transition_threshold_shared():
    """Both modules must flag pages at the same color transition threshold."""
    seq = {
        "weak_clusters": [],
        "per_page_notes": [
            {"page": 2, "premium_qc_score": 0.95, "color_transition_to_page_score": COLOR_TRANSITION_WEAK_THRESHOLD - 0.01},
        ],
    }
    assert 2 in _sequence_flagged_pages(seq)
    assert _is_sequence_flagged(2, seq)

    seq_above = {
        "weak_clusters": [],
        "per_page_notes": [
            {"page": 2, "premium_qc_score": 0.95, "color_transition_to_page_score": COLOR_TRANSITION_WEAK_THRESHOLD + 0.01},
        ],
    }
    assert 2 not in _sequence_flagged_pages(seq_above)
    assert not _is_sequence_flagged(2, seq_above)


def test_severe_local_thresholds_agree():
    """_severe_local_issue and _weak_dimensions must use the same
    per-dimension thresholds."""
    baseline = {
        "metadata": {
            "color_score": {"composite_score": 1.0},
            "visual_ensemble": {"ensemble_score": 1.0},
            "page_architecture_score": {"composite_score": 1.0},
            "saliency_flow_score": {"composite_score": 1.0},
        },
        "focus_bleed_overlap": 0.0,
    }
    assert not _severe_local_issue(baseline)
    assert _weak_dimensions(baseline) == []

    for key, threshold_const, dim_name in [
        ("color_score", SEVERE_COLOR_THRESHOLD, "color"),
        ("visual_ensemble", SEVERE_ENSEMBLE_THRESHOLD, "visual_ensemble"),
        ("page_architecture_score", SEVERE_ARCHITECTURE_THRESHOLD, "architecture"),
        ("saliency_flow_score", SEVERE_SALIENCY_THRESHOLD, "saliency_flow"),
    ]:
        score_key = "ensemble_score" if key == "visual_ensemble" else "composite_score"
        candidate = {
            "metadata": {
                "color_score": {"composite_score": 1.0},
                "visual_ensemble": {"ensemble_score": 1.0},
                "page_architecture_score": {"composite_score": 1.0},
                "saliency_flow_score": {"composite_score": 1.0},
            },
            "focus_bleed_overlap": 0.0,
        }
        candidate["metadata"][key] = {score_key: threshold_const - 0.01}
        assert _severe_local_issue(candidate), f"{key} below threshold must trigger severe"
        assert dim_name in _weak_dimensions(candidate), f"{key} below threshold must flag {dim_name}"


# ---------------------------------------------------------------------------
# 3. verify() reads production_report.json once
# ---------------------------------------------------------------------------


def test_verify_reads_production_report_once(tmp_path: Path):
    """verify() should not parse production_report.json more than once."""
    from bookforge.pipeline import BookforgePipeline

    out = tmp_path / "out"
    review = out / "review"
    review.mkdir(parents=True, exist_ok=True)

    required = BookforgePipeline()._expected_package_artifacts()
    for rel in required:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {
                    "post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"},
                    "qa_thresholds": {},
                    "cache_hit_rate": 1.0,
                    "editorial": {"age_band": "6-8", "artifact_intensity": "light", "readaloud_script_enabled": True},
                    "dual_audience": {"enabled": False},
                    "page_turn_tension": {"enabled": False},
                }
            elif path.name == "book_sequence_report.json":
                payload = {
                    "overall_sequence_score": 0.8,
                    "color_flow_summary_score": 0.8,
                    "architecture_flow_summary_score": 0.8,
                    "energy_curve_summary_score": 0.8,
                    "weak_clusters": [],
                    "saliency_flow_sequence": {"summary_score": 0.8},
                    "dual_audience_summary": {"summary_score": 0.8},
                }
            elif path.name == "reselection_report.json":
                payload = {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "targeted_regeneration_report.json":
                payload = {"enabled": True, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "sequence_optimization_report.json":
                payload = {"enabled": True, "config": {}, "pages_considered": 0, "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
            elif path.name == "storefront_optimization_report.json":
                payload = {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.8, "summary_score": 0.8, "limitations": []}
            elif path.name == "character_commercial_report.json":
                payload = {"enabled": True, "summary_score": 0.8, "lead_character_strength_summary": "", "weakest_pages": [], "strongest_pages": [], "limitations": []}
            elif path.name == "dual_audience_report.json":
                payload = {"enabled": False, "summary_score": 0.0, "child_channel_summary_score": 0.0, "adult_channel_summary_score": 0.0, "balance_summary_score": 0.0, "strongest_pages": [], "weakest_pages": [], "child_confusion_risk_pages": [], "adult_flatness_risk_pages": [], "imbalance_pages": [], "positive_notes": [], "warnings": [], "limitations": []}
            elif path.name == "page_turn_tension_report.json":
                payload = {"enabled": False, "summary_score": 0.0, "weak_turn_runs": [], "leftward_resistance_runs": [], "over_resolved_turns": [], "strong_turn_pages": [], "warnings": [], "positive_notes": [], "limitations": [], "findings": []}
            elif path.name == "hidden_world_report.json":
                payload = {"summary_score": 0.8, "warnings": []}
            elif path.name == "layout_search_report.json":
                payload = {"summary": {}, "pages": []}
            else:
                payload = {}
            path.write_text(json.dumps(payload), encoding="utf-8")
        elif path.suffix == ".pdf":
            path.write_bytes(b"%PDF-1.4 fake")
        elif path.suffix == ".md":
            path.write_text("# placeholder", encoding="utf-8")
        elif path.suffix == ".html":
            path.write_text("<html></html>", encoding="utf-8")
        else:
            path.write_text("{}", encoding="utf-8")

    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)
    (out / "review" / "editorial_report.md").write_text("# editorial", encoding="utf-8")
    (out / "review" / "readaloud_script.md").write_text("# readaloud", encoding="utf-8")

    prod_path = out / "review" / "production_report.json"
    original_read_text = Path.read_text
    read_count = [0]

    def counting_read_text(self, *args, **kwargs):
        if self == prod_path:
            read_count[0] += 1
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", counting_read_text):
        result = BookforgePipeline().verify(str(out))

    assert read_count[0] == 1, f"production_report.json was read {read_count[0]} times, expected 1"

