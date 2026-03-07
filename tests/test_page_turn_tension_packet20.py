from __future__ import annotations

import json

from PIL import Image, ImageDraw

from bookforge.page_turn import build_page_turn_tension_report, score_page_turn_tension
from bookforge.pipeline import BookforgePipeline
from bookforge.qc.image_qc import choose_best_variant
from bookforge.sequence_optimizer.scoring import local_score_bundle, sequence_summary_from_report


def _make_directional(path, right_heavy: bool = True):
    im = Image.new("RGB", (160, 100), (40, 40, 40))
    dr = ImageDraw.Draw(im)
    if right_heavy:
        dr.rectangle((80, 10, 155, 90), fill=(230, 220, 210))
        dr.line((40, 50, 140, 50), fill=(255, 255, 255), width=6)
    else:
        dr.rectangle((5, 10, 80, 90), fill=(230, 220, 210))
        dr.line((120, 50, 30, 50), fill=(255, 255, 255), width=6)
    im.save(path)


def _qa_row(page: int, score: float, resist: float):
    return {
        "page": page,
        "best": {
            "metadata": {
                "page_turn_tension_score": {
                    "page_turn_tension_score": score,
                    "turn_resistance_penalty": resist,
                    "confidence": 0.7,
                    "warnings": [],
                    "notes": ["proxy"],
                }
            }
        },
    }


def test_scoring_proxy_bounds_and_directionality(tmp_path):
    r = tmp_path / "right.png"
    l = tmp_path / "left.png"
    _make_directional(r, True)
    _make_directional(l, False)

    right = score_page_turn_tension(r, page_number=2, page_count=6, page_text="What happens next?")
    left = score_page_turn_tension(l, page_number=2, page_count=6, page_text="The end.")

    assert 0.0 <= right.page_turn_tension_score <= 1.0
    assert 0.0 <= left.page_turn_tension_score <= 1.0
    assert right.page_turn_tension_score >= left.page_turn_tension_score


def test_choose_best_variant_attaches_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKFORGE_PAGE_TURN_TENSION", "true")
    p = tmp_path / "v1.png"
    _make_directional(p, True)

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
        page_count=8,
        page_text="Who is there?",
    )
    assert best.exists()
    turn = ((qa["best"].get("metadata") or {}).get("page_turn_tension_score") or {})
    assert "page_turn_tension_score" in turn and "turn_resistance_penalty" in turn


def test_sequence_report_and_verify_schema(tmp_path):
    report = build_page_turn_tension_report(
        page_count=6,
        qa_attempts=[
            _qa_row(1, 0.7, 0.2),
            _qa_row(2, 0.35, 0.7),
            _qa_row(3, 0.33, 0.71),
            _qa_row(4, 0.77, 0.3),
            _qa_row(5, 0.74, 0.32),
            _qa_row(6, 0.28, 0.63),
        ],
        enabled=True,
    )
    assert report.summary_score > 0.0
    assert report.leftward_resistance_runs
    assert report.weak_turn_runs

    out = tmp_path / "out"
    out.mkdir(parents=True)
    req = BookforgePipeline()._expected_package_artifacts()
    assert "review/book_quality_report.json" in req

    for rel in req:
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            payload = {}
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "dual_audience": {"enabled": True}, "page_turn_tension": {"enabled": True}}
            elif path.name == "book_quality_report.json":
                payload = {"schema_version": "1.0", "generated_at": "2024-01-01T00:00:00Z", "artifact": "book_quality_report.json", "summary_scores": {"overall_sequence_score": 0.5, "color_flow_summary_score": 0.5, "architecture_flow_summary_score": 0.5, "energy_curve_summary_score": 0.5}, "warnings": [], "limitations": [], "per_page_notes": [], "sequence_findings": {}, "actions_taken": {}, "legacy_artifacts": {}}
            elif path.name == "book_sequence_report.json":
                payload = {"overall_sequence_score": 0.9, "color_flow_summary_score": 0.9, "architecture_flow_summary_score": 0.9, "energy_curve_summary_score": 0.9, "weak_clusters": [], "saliency_flow_sequence": {}, "dual_audience_summary": {"summary_score": 0.7}, "page_turn_tension_summary": {"summary_score": 0.55}}
            elif path.name == "reselection_report.json":
                payload = {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "targeted_regeneration_report.json":
                payload = {"enabled": False, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}}
            elif path.name == "sequence_optimization_report.json":
                payload = {"enabled": False, "config": {}, "pages_considered": [], "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
            elif path.name == "character_commercial_report.json":
                payload = {"enabled": True, "summary_score": 0.5, "lead_character_strength_summary": "ok", "weakest_pages": [], "strongest_pages": [], "limitations": []}
            elif path.name == "dual_audience_report.json":
                payload = {"enabled": True, "summary_score": 0.7, "child_channel_summary_score": 0.6, "adult_channel_summary_score": 0.7, "balance_summary_score": 0.65, "strongest_pages": [], "weakest_pages": [], "child_confusion_risk_pages": [], "adult_flatness_risk_pages": [], "imbalance_pages": [], "positive_notes": [], "warnings": [], "limitations": []}
            elif path.name == "hidden_world_report.json":
                payload = {"summary_score": 0.6, "warnings": []}
            elif path.name == "layout_search_report.json":
                payload = {"status": "PASS", "config": {}, "pages": [], "summary": {"entries": 0, "mean_top_score": 0.0, "total_rejected": 0, "notes": []}, "sequence_notes": []}
            elif path.name == "storefront_optimization_report.json":
                payload = {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.5, "summary_score": 0.5, "limitations": []}
            elif path.name == "page_turn_tension_report.json":
                payload = report.to_dict()
            path.write_text(json.dumps(payload), encoding="utf-8")
        elif path.suffix == ".md":
            path.write_text("ok", encoding="utf-8")
        else:
            path.write_bytes(b"x")

    (out / "review" / "thumbs").mkdir(parents=True, exist_ok=True)
    verify = BookforgePipeline().verify(str(out))
    assert verify["status"] in {"PASS", "WARN"}
    assert not [f for f in verify["failures"] if "page_turn_tension_report" in f]


def test_sequence_optimizer_compatibility_signal():
    candidate = {"metadata": {"page_turn_tension_score": {"page_turn_tension_score": 0.8}}}
    bundle = local_score_bundle(candidate)
    assert "page_turn_tension" in bundle

    summary = sequence_summary_from_report({"page_turn_tension_summary": {"summary_score": 0.61}})
    assert summary["page_turn_tension_summary_score"] == 0.61
