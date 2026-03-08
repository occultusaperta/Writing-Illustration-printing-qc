import json
from pathlib import Path

from bookforge.pipeline import BookforgePipeline
from bookforge.review.book_quality import build_book_quality_report, validate_book_quality_report


def _legacy_minimal_payload(name: str):
    if name == "book_sequence_report.json":
        return {
            "overall_sequence_score": 0.9,
            "color_flow_summary_score": 0.8,
            "architecture_flow_summary_score": 0.7,
            "energy_curve_summary_score": 0.6,
            "summary_notes": [],
            "warnings": [],
            "limitations": [],
            "per_page_notes": [],
            "weak_clusters": [],
            "color_transitions": [],
            "architecture_flow": {},
            "energy_curve": {},
            "camera_sequence": {},
            "saliency_flow_sequence": {},
            "typography_sequence": {},
            "hidden_world_sequence": {},
            "dual_audience_summary": {},
            "page_turn_tension_summary": {},
        }
    if name == "layout_search_report.json":
        return {"summary": {"summary_score": 0.5}, "pages": []}
    if name == "typography_report.json":
        return {"summary_score": 0.4, "warnings": [], "limitations": []}
    if name == "reselection_report.json":
        return {"config": {}, "considered_pages": [], "eligible_pages": [], "replaced_pages": [], "decisions": [], "sequence_improvement": {}}
    if name == "targeted_regeneration_report.json":
        return {"enabled": False, "config": {}, "eligible_targets": [], "decisions": [], "sequence_improvement": {}, "warnings": [], "limitations": []}
    if name == "sequence_optimization_report.json":
        return {"enabled": False, "config": {}, "pages_considered": [], "candidate_moves_considered": 0, "accepted_moves": [], "rejected_moves": [], "cap_hit": False, "before_summary": {}, "after_summary": {}, "net_improvement": {}}
    if name == "hidden_world_report.json":
        return {"summary_score": 0.4, "warnings": [], "limitations": []}
    if name == "storefront_optimization_report.json":
        return {"enabled": True, "look_inside": {}, "first_pages_strength_score": 0.5, "summary_score": 0.5, "warnings": [], "limitations": []}
    if name == "character_commercial_report.json":
        return {"enabled": True, "summary_score": 0.5, "lead_character_strength_summary": "Moderate", "weakest_pages": [], "strongest_pages": [], "warnings": [], "limitations": []}
    if name == "dual_audience_report.json":
        return {"enabled": False, "summary_score": 0.0, "child_channel_summary_score": 0.0, "adult_channel_summary_score": 0.0, "balance_summary_score": 0.0, "strongest_pages": [], "weakest_pages": [], "child_confusion_risk_pages": [], "adult_flatness_risk_pages": [], "imbalance_pages": [], "positive_notes": [], "warnings": [], "limitations": []}
    if name == "page_turn_tension_report.json":
        return {"enabled": False, "summary_score": 0.0, "weak_turn_runs": [], "leftward_resistance_runs": [], "over_resolved_turns": [], "strong_turn_pages": [], "warnings": [], "positive_notes": [], "limitations": [], "findings": []}
    return {}


def test_book_quality_schema_validity(tmp_path: Path):
    review = tmp_path / "review"
    review.mkdir(parents=True)
    (review / "production_report.json").write_text(json.dumps({"dual_audience": {"enabled": True}, "page_turn_tension": {"enabled": True}}), encoding="utf-8")
    for name in [
        "book_sequence_report.json",
        "layout_search_report.json",
        "typography_report.json",
        "reselection_report.json",
        "targeted_regeneration_report.json",
        "sequence_optimization_report.json",
        "hidden_world_report.json",
        "storefront_optimization_report.json",
        "character_commercial_report.json",
        "dual_audience_report.json",
        "page_turn_tension_report.json",
    ]:
        (review / name).write_text(json.dumps(_legacy_minimal_payload(name)), encoding="utf-8")

    payload = build_book_quality_report(review)
    assert validate_book_quality_report(payload) == []


def test_verify_generates_master_from_legacy_when_missing(tmp_path: Path):
    out = tmp_path / "out"
    required = BookforgePipeline()._expected_package_artifacts()
    for rel in required:
        if rel == "review/book_quality_report.json":
            continue
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            if path.name == "preflight_report.json":
                payload = {"status": "PASS"}
            elif path.name == "production_report.json":
                payload = {"post": {"crop_mode": "smart", "director_grade_enabled": True, "tone_curve_preset": "storybook_lux"}, "qa_thresholds": {}, "cache_hit_rate": 1.0, "editorial": {"age_band": "6-8", "artifact_intensity": "light", "readaloud_script_enabled": False}, "dual_audience": {"enabled": False}, "page_turn_tension": {"enabled": False}}
            else:
                payload = _legacy_minimal_payload(path.name)
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            path.write_bytes(b"x")

    (out / "review" / "editorial_report.md").write_text("x", encoding="utf-8")
    thumbs = out / "review" / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    (thumbs / "cover.jpg").write_bytes(b"x")

    result = BookforgePipeline().verify(str(out))
    assert result["status"] in {"PASS", "WARN"}
    assert (out / "review" / "book_quality_report.json").exists()
    assert any("compatibility-mode" in w for w in result.get("warnings", []))


def test_book_quality_disabled_feature_limitations(tmp_path: Path):
    review = tmp_path / "review"
    review.mkdir(parents=True)
    (review / "production_report.json").write_text(json.dumps({"dual_audience": {"enabled": False}, "page_turn_tension": {"enabled": False}}), encoding="utf-8")
    (review / "book_sequence_report.json").write_text(json.dumps(_legacy_minimal_payload("book_sequence_report.json")), encoding="utf-8")
    payload = build_book_quality_report(review)
    limitation_messages = [row.get("message", "") for row in payload.get("limitations", [])]
    assert any("Dual-audience analysis disabled" in msg for msg in limitation_messages)
    assert any("Page-turn tension analysis disabled" in msg for msg in limitation_messages)
