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


def test_image_qc_ranking_restores_bounded_character_and_dual_tiebreaks() -> None:
    ranking = scoring_registry().image_qc_ranking
    assert ranking.character_tiebreak_weight > 0.0
    assert 0.0 < ranking.character_tiebreak_floor < 1.0
    assert 0.0 < ranking.character_tiebreak_confidence_floor < 1.0
    assert ranking.dual_audience_tiebreak_weight > 0.0
    assert 0.0 < ranking.dual_audience_tiebreak_floor < 1.0


def test_bounded_tiebreaks_change_ordering_in_close_candidates() -> None:
    ranking = scoring_registry().image_qc_ranking

    def key(report):
        meta = report.get("metadata") or {}

        def bounded(raw, floor, weight):
            bounded_score = max(0.0, min(1.0, float(raw)))
            if bounded_score < floor:
                return 0.0
            return weight * (bounded_score - floor) / (1.0 - floor)

        character = meta.get("character_commercial_score") or {}
        character_weight = ranking.character_tiebreak_weight if float(character.get("confidence", 0.0) or 0.0) >= ranking.character_tiebreak_confidence_floor else 0.0
        return (
            True,
            0.0,
            1.0,
            10.0,
            0.0,
            0.5,
            0.5,
            0.5,
            bounded(character.get("composite_score", 0.0), ranking.character_tiebreak_floor, character_weight),
            bounded(((meta.get("dual_audience_score") or {}).get("composite_score", 0.0)), ranking.dual_audience_tiebreak_floor, ranking.dual_audience_tiebreak_weight),
        )

    candidate_lo = {
        "metadata": {
            "character_commercial_score": {"composite_score": 0.52, "confidence": 0.8},
            "dual_audience_score": {"composite_score": 0.56},
        }
    }
    candidate_hi = {
        "metadata": {
            "character_commercial_score": {"composite_score": 0.91, "confidence": 0.86},
            "dual_audience_score": {"composite_score": 0.9},
        }
    }

    ranked = sorted([candidate_lo, candidate_hi], key=key, reverse=True)
    assert ranked[0] is candidate_hi


def test_page_turn_signal_is_metadata_only_for_image_qc_ranking() -> None:
    ranking = scoring_registry().image_qc_ranking
    assert not hasattr(ranking, "page_turn_tiebreak_weight")
