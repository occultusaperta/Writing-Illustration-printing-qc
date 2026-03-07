from __future__ import annotations

from pathlib import Path

from PIL import Image

from bookforge.qc.image_qc import choose_best_variant
from bookforge.review import reselection
from bookforge.scoring_registry import scoring_registry
from bookforge.sequence_optimizer.scoring import local_score_bundle, transition_fit


def test_sequence_optimizer_local_score_preserves_default_behavior() -> None:
    candidate = {
        "focus_bleed_overlap": 0.15,
        "metadata": {
            "color_score": {"composite_score": 0.8},
            "visual_ensemble": {"ensemble_score": 0.7},
            "page_architecture_score": {"composite_score": 0.6},
            "saliency_flow_score": {"composite_score": 0.5},
            "shot_adherence_score": {"composite_score": 0.4},
            "hidden_world_score": {"composite_score": 0.3},
            "character_commercial_score": {"composite_score": 0.2},
            "dual_audience_score": {"composite_score": 0.9},
            "page_turn_tension_score": {"page_turn_tension_score": 0.1},
        },
    }
    bundle = local_score_bundle(candidate)
    assert round(bundle["local_composite"], 6) == 0.5995


def test_transition_target_shared_across_reselection_and_sequence_optimizer() -> None:
    seq_report = {
        "color_transitions": [
            {
                "to_page": 2,
                "expected_mode": "hard_cut",
                "expected_strength": 0.5,
            }
        ]
    }
    candidate = {
        "page_to_page_hist_drift": scoring_registry().transition_targets.hard_cut_floor,
        "metadata": {
            "visual_ensemble": {"ensemble_score": 0.6},
            "page_architecture_score": {"composite_score": 0.7},
        },
    }
    seq_opt_fit = transition_fit(2, candidate, seq_report)
    reselection_support = reselection._score_sequence_support(2, candidate, seq_report)
    assert seq_opt_fit == 1.0
    assert reselection_support >= 0.5


def test_feature_flags_disabled_skip_optional_metadata(monkeypatch, tmp_path: Path) -> None:
    for env_name in [
        "BOOKFORGE_CHARACTER_COMMERCIAL_SCORING",
        "BOOKFORGE_SALIENCY_FLOW",
        "BOOKFORGE_DUAL_AUDIENCE",
        "BOOKFORGE_PAGE_TURN_TENSION",
    ]:
        monkeypatch.setenv(env_name, "false")

    image = tmp_path / "variant.png"
    Image.new("RGB", (64, 64), color=(200, 120, 90)).save(image)
    qa = {
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
    _, payload = choose_best_variant(
        [image],
        qa,
        style_ref=None,
        prev_ref=None,
        page_number=1,
        page_count=1,
    )
    metadata = payload["best"].get("metadata", {})
    assert "character_commercial_score" not in metadata
    assert "saliency_flow_score" not in metadata
    assert "dual_audience_score" not in metadata
    assert "page_turn_tension_score" not in metadata
