from __future__ import annotations

import json
from pathlib import Path

from bookforge.hidden_world import (
    build_hidden_world_guidance,
    build_hidden_world_prompt_lines,
    build_hidden_world_sequence_finding,
    plan_hidden_world_sequence,
    score_hidden_world_adherence,
)
from bookforge.pipeline import _build_planning_prompt_guidance


def test_storyweaver_hidden_detail_extraction_priority_and_recurrence() -> None:
    pages = [
        {
            "page_number": 1,
            "text": "A",
            "required_hidden_details": ["tiny blue fox"],
            "illustration_notes": "Hidden detail: tiny blue fox; Foreshadow: silver key in shelf",
        },
        {
            "page_number": 2,
            "text": "B",
            "required_hidden_details": [],
            "illustration_notes": "Callback: blue fox seen again in fabric pattern",
        },
    ]
    plan = plan_hidden_world_sequence(pages=pages)
    assert plan.page_count == 2
    assert any(d.detail_type.value == "required" and d.detail_text == "tiny blue fox" for d in plan.detail_plans)
    assert "tiny blue fox" in plan.recurring_motifs


def test_prompt_metadata_generation_contains_discoverable_not_dominant() -> None:
    page_plan = {
        "required_details": ["tiny moon token"],
        "recurring_motifs": ["tiny moon token"],
        "foreshadowing_hints": ["foreshadow old map"],
        "callback_hints": ["callback old map"],
        "parent_reward_details": ["woodgrain face echo"],
        "visibility_targets": {"tiny moon token": "subtle"},
        "discoverable_not_dominant": True,
    }
    guidance = build_hidden_world_guidance(page_plan)
    lines = build_hidden_world_prompt_lines(guidance)
    merged = " ".join(lines).lower()
    assert "discoverable but not dominant" in merged
    assert "required hidden details" in merged


def test_hidden_world_score_schema_and_bounds() -> None:
    score = score_hidden_world_adherence(
        page_number=3,
        hidden_world_guidance={"required_details": ["tiny bird"], "recurring_motifs": ["tiny bird"]},
        prompt_metadata={"hidden_world_guidance": {"required_details": ["tiny bird"]}},
        saliency_score={"composite_score": 0.6},
        architecture_variant={"zones": [{"zone_type": "text", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}]},
        illustration_notes="Hidden detail: tiny bird",
    )
    payload = score.to_dict()
    for field in [
        "required_detail_presence_score",
        "recurrence_consistency_score",
        "subtlety_score",
        "parent_reward_score",
        "foreshadowing_callback_score",
        "text_collision_risk_score",
        "composite_score",
        "confidence",
    ]:
        assert 0.0 <= float(payload[field]) <= 1.0


def test_sequence_diagnostics_schema() -> None:
    finding = build_hidden_world_sequence_finding(
        page_count=2,
        hidden_world_plan={"recurring_motifs": ["tiny fox"], "detail_plans": [{"detail_type": "recurring_motif", "detail_text": "tiny fox", "page_numbers": [1, 2]}]},
        qa_attempts=[
            {"page": 1, "best": {"metadata": {"hidden_world_score": {"composite_score": 0.8, "subtlety_score": 0.7, "recurrence_consistency_score": 0.8, "parent_reward_score": 0.7, "foreshadowing_callback_score": 0.7, "required_detail_presence_score": 0.9}}}},
            {"page": 2, "best": {"metadata": {"hidden_world_score": {"composite_score": 0.75, "subtlety_score": 0.6, "recurrence_consistency_score": 0.75, "parent_reward_score": 0.6, "foreshadowing_callback_score": 0.7, "required_detail_presence_score": 0.85}}}},
        ],
    )
    payload = finding.to_dict()
    assert "summary_score" in payload
    assert "recurring_motif_continuity_notes" in payload


def test_safe_noop_when_hidden_world_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOOKFORGE_HIDDEN_WORLD", "false")
    out = tmp_path / "run"
    (out / "preprod" / "planning").mkdir(parents=True)
    (out / "preprod" / "planning" / "color_script.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    (out / "preprod" / "planning" / "emotion_analysis.json").write_text("[]", encoding="utf-8")
    (out / "preprod" / "planning" / "architecture_plan.json").write_text("[]", encoding="utf-8")
    (out / "preprod" / "planning" / "camera_sequence_plan.json").write_text(json.dumps({"pages": []}), encoding="utf-8")
    guidance = _build_planning_prompt_guidance(out)
    assert isinstance(guidance, dict)


def test_pipeline_prompt_guidance_additive_hidden_world_integration(tmp_path: Path) -> None:
    out = tmp_path / "run"
    planning = out / "preprod" / "planning"
    planning.mkdir(parents=True)
    (planning / "color_script.json").write_text(json.dumps({"pages": [{"page_number": 1}]}), encoding="utf-8")
    (planning / "emotion_analysis.json").write_text(json.dumps([{"page_number": 1}]), encoding="utf-8")
    (planning / "architecture_plan.json").write_text(json.dumps([{"page_number": 1, "selected_variant_id": "full_bleed_single_primary"}]), encoding="utf-8")
    (planning / "camera_sequence_plan.json").write_text(json.dumps({"pages": [{"page_number": 1, "shot_type": "closeup_emotion"}]}), encoding="utf-8")
    (planning / "hidden_world_plan.json").write_text(
        json.dumps({"pages": [{"page_number": 1, "required_details": ["tiny fox"], "recurring_motifs": ["tiny fox"], "discoverable_not_dominant": True}]}),
        encoding="utf-8",
    )
    guidance = _build_planning_prompt_guidance(out)
    assert 1 in guidance
    assert "hidden_world_guidance" in guidance[1]
    assert any("discoverable" in line.lower() for line in guidance[1].get("prompt_lines", []))
