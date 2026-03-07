from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from bookforge.pipeline import BookforgePipeline
from bookforge.review.targeted_regeneration import (
    apply_targeted_regeneration_decisions,
    run_targeted_regeneration,
    with_sequence_improvement,
    write_targeted_regeneration_report,
)


def _img(path: Path, tone: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), (tone, tone, tone)).save(path)


def _sequence_report() -> dict:
    return {
        "overall_sequence_score": 0.69,
        "weak_clusters": [{"severity": "warning", "pages": [1]}],
        "per_page_notes": [{"page": 1, "premium_qc_score": 0.72, "color_transition_to_page_score": 0.66}],
        "color_transitions": [{"to_page": 1, "expected_mode": "blend", "expected_strength": 0.5}],
    }


def _qa_attempt(best_path: str) -> dict:
    best = {
        "path": best_path,
        "focus_bleed_overlap": 0.18,
        "page_to_page_hist_drift": 0.03,
        "metadata": {
            "color_score": {"composite_score": 0.61},
            "visual_ensemble": {"ensemble_score": 0.62},
            "page_architecture_score": {"composite_score": 0.60},
        },
    }
    return {"page": 1, "attempt": 2, "best": best, "variants": [best], "passes": False}


def test_noop_when_disabled_or_missing_sequence(tmp_path: Path):
    b = tmp_path / "best.png"
    _img(b, 80)
    report = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style"}],
        qa_attempts=[_qa_attempt(str(b))],
        sequence_report=None,
        reselection_report={},
        planning_prompt_guidance={1: {"prompt_lines": ["palette A"]}},
        lock_context={"negative_prompt": "no text"},
        provider_available=True,
    )
    assert report.enabled is False
    assert report.decisions == []


def test_noop_when_no_eligible_pages(tmp_path: Path):
    b = tmp_path / "best.png"
    _img(b, 100)
    qa = _qa_attempt(str(b))
    qa["best"]["focus_bleed_overlap"] = 0.01
    qa["best"]["metadata"]["color_score"]["composite_score"] = 0.9
    qa["best"]["metadata"]["visual_ensemble"]["ensemble_score"] = 0.9
    qa["best"]["metadata"]["page_architecture_score"]["composite_score"] = 0.9
    report = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style"}],
        qa_attempts=[qa],
        sequence_report={"overall_sequence_score": 0.8, "weak_clusters": [], "per_page_notes": [], "color_transitions": []},
        reselection_report={"decisions": []},
        planning_prompt_guidance={1: {"prompt_lines": ["palette A"]}},
        lock_context={"negative_prompt": "no text"},
        provider_available=True,
    )
    assert report.enabled is True
    assert report.eligible_targets == []


def test_noop_when_provider_unavailable(tmp_path: Path):
    b = tmp_path / "best.png"
    _img(b, 80)
    report = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style"}],
        qa_attempts=[_qa_attempt(str(b))],
        sequence_report=_sequence_report(),
        reselection_report={"decisions": [{"page": 1, "replaced": False}]},
        planning_prompt_guidance={1: {"prompt_lines": ["palette A"]}},
        lock_context={"negative_prompt": "no text"},
        provider_available=False,
    )
    assert report.enabled is True
    assert report.decisions == []


def test_request_preserves_lock_and_planning_context(tmp_path: Path):
    b = tmp_path / "best.png"
    _img(b, 80)
    report = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style prompt"}],
        qa_attempts=[_qa_attempt(str(b))],
        sequence_report=_sequence_report(),
        reselection_report={"decisions": [{"page": 1, "replaced": False}]},
        planning_prompt_guidance={1: {"prompt_lines": ["planA"], "negative_lines": ["avoid clutter"]}},
        lock_context={"negative_prompt": "never add text", "approved_character_reference": "char.png"},
        provider_available=True,
    )
    req = report.decisions[0].request
    assert req is not None
    assert req.lock_context["approved_character_reference"] == "char.png"
    assert req.planning_context["prompt_lines"] == ["planA"]


def test_replacement_when_measurable_improvement_exists(tmp_path: Path):
    b = tmp_path / "best.png"
    c = tmp_path / "cand.png"
    _img(b, 60)
    _img(c, 200)
    run = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style prompt"}],
        qa_attempts=[_qa_attempt(str(b))],
        sequence_report=_sequence_report(),
        reselection_report={"decisions": [{"page": 1, "replaced": False}]},
        planning_prompt_guidance={1: {}},
        lock_context={"negative_prompt": "never add text"},
        provider_available=True,
        minimum_required_improvement=0.03,
    )
    applied = apply_targeted_regeneration_decisions(
        selected=[str(b)],
        report=run,
        sequence_report=_sequence_report(),
        previous_candidates={1: _qa_attempt(str(b))["best"]},
        generated_candidates={
            1: {
                "path": str(c),
                "page_to_page_hist_drift": 0.06,
                "metadata": {
                    "color_score": {"composite_score": 0.93},
                    "visual_ensemble": {"ensemble_score": 0.92},
                    "page_architecture_score": {"composite_score": 0.9},
                },
            }
        },
    )
    assert applied.replaced_targets == ["page:1"]


def test_rejection_when_improvement_insufficient_and_cap(tmp_path: Path):
    b = tmp_path / "best.png"
    c = tmp_path / "cand.png"
    _img(b, 80)
    _img(c, 90)
    run = run_targeted_regeneration(
        selected=[str(b)],
        prompts=[{"page_number": 1, "prompt": "locked style prompt"}],
        qa_attempts=[_qa_attempt(str(b))],
        sequence_report=_sequence_report(),
        reselection_report={"decisions": [{"page": 1, "replaced": False}]},
        planning_prompt_guidance={1: {}},
        lock_context={"negative_prompt": "never add text"},
        provider_available=True,
        max_regenerations_per_run=0,
    )
    assert run.decisions == []
    assert run.replacement_cap_hit is False


def test_report_schema_and_pipeline_artifact(tmp_path: Path):
    out = tmp_path / "review" / "targeted_regeneration_report.json"
    report = run_targeted_regeneration(
        selected=[],
        prompts=[],
        qa_attempts=[],
        sequence_report=None,
        reselection_report=None,
        planning_prompt_guidance={},
        lock_context={},
        provider_available=False,
    )
    report = with_sequence_improvement(report, before_score=None, after_score=None, re_evaluated=False)
    write_targeted_regeneration_report(out, report)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "config" in payload
    assert "decisions" in payload
    assert "sequence_improvement" in payload
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/book_quality_report.json" in required
