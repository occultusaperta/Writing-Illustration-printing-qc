from __future__ import annotations

import json

from bookforge.dual_audience import build_dual_audience_report, score_dual_audience
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.image_qc import choose_best_variant
from bookforge.sequence_optimizer import run_sequence_optimization


def _report(*, entropy=5.2, face_like=1, text_like=0.02, drift=0.1, saliency=0.8, ensemble=0.75, arch=0.7, color=0.7, shot=0.72, hidden=0.68):
    return {
        "path": "/tmp/x.png",
        "entropy": entropy,
        "focus_bleed_overlap": 0.06,
        "face_like_regions": face_like,
        "text_likelihood": text_like,
        "page_to_page_hist_drift": drift,
        "style_hist_similarity": 0.82,
        "border_artifact_score": 0.05,
        "metadata": {
            "saliency_flow_score": {"primary_focus_score": saliency, "fixation_order_score": saliency - 0.08, "text_quietness_score": 0.76, "composite_score": saliency},
            "shot_adherence_score": {"composite_score": shot, "framing_scale_score": shot, "angle_alignment_score": shot, "shot_type": "closeup_emotion"},
            "visual_ensemble": {
                "ensemble_score": ensemble,
                "critic_scores": {
                    "composition_score": ensemble,
                    "clarity_score": ensemble - 0.06,
                    "texture_score": ensemble - 0.04,
                    "artifact_score": ensemble - 0.03,
                    "perceptual_quality": ensemble - 0.05,
                },
            },
            "page_architecture_score": {"composite_score": arch},
            "color_score": {"composite_score": color},
            "hidden_world_score": {"composite_score": hidden, "subtlety_score": hidden, "parent_reward_score": hidden, "recurrence_consistency_score": hidden, "foreshadowing_callback_score": hidden},
            "character_commercial_score": {"composite_score": 0.6},
        },
    }


def test_score_bounds_and_balance_penalty():
    strong = score_dual_audience(_report())
    weak = score_dual_audience(_report(saliency=0.2, ensemble=0.25, arch=0.22, color=0.2, shot=0.2, hidden=0.2))
    for v in [strong.composite_score, strong.child_channel_score.composite_score, strong.adult_channel_score.composite_score, strong.balance_score, weak.composite_score]:
        assert 0.0 <= v <= 1.0
    assert weak.composite_score < strong.composite_score


def test_child_channel_favors_clear_scene_over_cluttered():
    clear = score_dual_audience(_report(entropy=5.0, saliency=0.84, face_like=1))
    cluttered = score_dual_audience(_report(entropy=8.9, saliency=0.44, face_like=5, text_like=0.18))
    assert clear.child_channel_score.composite_score > cluttered.child_channel_score.composite_score


def test_adult_channel_rewards_polish_and_composition():
    polished = score_dual_audience(_report(ensemble=0.9, arch=0.86, color=0.84, hidden=0.76))
    flat = score_dual_audience(_report(ensemble=0.36, arch=0.35, color=0.3, hidden=0.3, drift=0.5))
    assert polished.adult_channel_score.composite_score > flat.adult_channel_score.composite_score


def test_report_noop_when_disabled():
    rep = build_dual_audience_report(page_count=3, qa_attempts=[], enabled=False)
    assert rep.enabled is False
    assert rep.summary_score == 0.0


def test_metadata_attachment_and_schema_via_choose_best_variant(monkeypatch, tmp_path):
    from PIL import Image

    monkeypatch.setenv("BOOKFORGE_DUAL_AUDIENCE", "true")
    p = tmp_path / "v1.png"
    Image.new("RGB", (64, 64), (120, 140, 170)).save(p)
    best, qa = choose_best_variant(
        [p],
        qa_config={
            "min_sharpness": 0.0,
            "min_entropy": 0.0,
            "min_contrast": 0.0,
            "max_border_bar_score": 1.0,
            "max_text_likelihood": 1.0,
            "max_watermark_likelihood": 1.0,
            "max_logo_likelihood": 1.0,
            "max_border_artifact_score": 1.0,
            "max_face_like_regions": 99,
            "min_style_hist_similarity": 0.0,
            "max_page_to_page_hist_drift": 1.0,
            "max_focus_bleed_overlap": 1.0,
            "max_regen_rounds": 1,
        },
        style_ref=None,
        prev_ref=None,
        page_number=1,
    )
    assert best.exists()
    dual = ((qa["best"].get("metadata") or {}).get("dual_audience_score") or {})
    assert "child_channel_score" in dual and "adult_channel_score" in dual and "composite_score" in dual


def test_review_artifact_schema_verify_and_package_inclusion(tmp_path):
    out = tmp_path / "out"
    out.mkdir(parents=True)
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/dual_audience_report.json" in required

    for rel in required:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            payload = {}
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "dual_audience": {"enabled": True}, "page_turn_tension": {"enabled": False}}
            elif path.name == "book_sequence_report.json":
                payload = {"overall_sequence_score": 0.9, "color_flow_summary_score": 0.9, "architecture_flow_summary_score": 0.9, "energy_curve_summary_score": 0.9, "weak_clusters": [], "saliency_flow_sequence": {}, "dual_audience_summary": {"summary_score": 0.7}}
            elif path.name == "reselection_report.json":
                payload = {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "targeted_regeneration_report.json":
                payload = {"enabled": False, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "storefront_optimization_report.json":
                payload = {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.5, "summary_score": 0.5, "limitations": []}
            elif path.name == "hidden_world_report.json":
                payload = {"summary_score": 0.5, "warnings": []}
            elif path.name == "character_commercial_report.json":
                payload = {"enabled": True, "summary_score": 0.5, "lead_character_strength_summary": "Moderate", "weakest_pages": [], "strongest_pages": [], "limitations": []}
            elif path.name == "layout_search_report.json":
                payload = {"summary": {}, "pages": []}
            elif path.name == "sequence_optimization_report.json":
                payload = {"enabled": False, "config": {}, "pages_considered": [], "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
            elif path.name == "dual_audience_report.json":
                payload = {"enabled": True, "summary_score": 0.6, "child_channel_summary_score": 0.6, "adult_channel_summary_score": 0.58, "balance_summary_score": 0.8, "strongest_pages": [], "weakest_pages": [], "child_confusion_risk_pages": [], "adult_flatness_risk_pages": [], "imbalance_pages": [], "positive_notes": [], "warnings": [], "limitations": []}
            elif path.name == "page_turn_tension_report.json":
                payload = {"enabled": False, "summary_score": 0.0, "weak_turn_runs": [], "leftward_resistance_runs": [], "over_resolved_turns": [], "strong_turn_pages": [], "warnings": [], "positive_notes": [], "limitations": [], "findings": []}
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"x")

    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)
    (out / "review" / "thumbs" / "cover.jpg").write_bytes(b"x")
    res = BookforgePipeline().verify(str(out))
    assert res["status"] in {"PASS", "WARN"}


def test_packet18_sequence_optimizer_compatibility_uses_dual_signal(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    seq = {
        "overall_sequence_score": 0.62,
        "color_flow_summary_score": 0.58,
        "architecture_flow_summary_score": 0.6,
        "weak_clusters": [],
        "color_transitions": [],
        "camera_sequence": {"summary_score": 0.61},
        "saliency_flow_sequence": {"summary_score": 0.57},
        "typography_sequence": {"summary_score": 0.54},
        "hidden_world_sequence": {"summary_score": 0.52},
        "character_commercial_summary": {"summary_score": 0.59},
        "layout_search_summary": {"summary_score": 0.56},
        "dual_audience_summary": {"summary_score": 0.68},
        "per_page_notes": [{"page": 2, "premium_qc_score": 0.74}],
    }
    qa = [{"page": 2, "attempt": 1, "best": _report()["metadata"] and {
        "path": "/x/current.png", "focus_bleed_overlap": 0.2, "page_to_page_hist_drift": 0.4,
        "metadata": {
            "color_score": {"composite_score": 0.5}, "visual_ensemble": {"ensemble_score": 0.5}, "page_architecture_score": {"composite_score": 0.5},
            "saliency_flow_score": {"composite_score": 0.5}, "shot_adherence_score": {"composite_score": 0.5}, "hidden_world_score": {"composite_score": 0.5},
            "character_commercial_score": {"composite_score": 0.5}, "dual_audience_score": {"composite_score": 0.4}
        }
    }, "variants": [
        {
            "path": "/x/current.png", "focus_bleed_overlap": 0.2, "page_to_page_hist_drift": 0.4,
            "metadata": {"color_score": {"composite_score": 0.5}, "visual_ensemble": {"ensemble_score": 0.5}, "page_architecture_score": {"composite_score": 0.5}, "saliency_flow_score": {"composite_score": 0.5}, "shot_adherence_score": {"composite_score": 0.5}, "hidden_world_score": {"composite_score": 0.5}, "character_commercial_score": {"composite_score": 0.5}, "dual_audience_score": {"composite_score": 0.4}}
        },
        {
            "path": "/x/up.png", "focus_bleed_overlap": 0.05, "page_to_page_hist_drift": 0.2,
            "metadata": {"color_score": {"composite_score": 0.8}, "visual_ensemble": {"ensemble_score": 0.8}, "page_architecture_score": {"composite_score": 0.8}, "saliency_flow_score": {"composite_score": 0.8}, "shot_adherence_score": {"composite_score": 0.8}, "hidden_world_score": {"composite_score": 0.8}, "character_commercial_score": {"composite_score": 0.8}, "dual_audience_score": {"composite_score": 0.85}}
        }
    ]}]
    rep = run_sequence_optimization(selected=["/x/a.png", "/x/current.png", "/x/c.png"], qa_attempts=qa, sequence_report=seq)
    assert rep.enabled is True
