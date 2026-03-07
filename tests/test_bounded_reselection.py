from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from bookforge.pipeline import BookforgePipeline
from bookforge.review.reselection import (
    apply_reselection_decisions,
    run_bounded_reselection,
    with_sequence_improvement,
    write_reselection_report,
)


def _img(path: Path, tone: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), (tone, tone, tone)).save(path)


def _qa_attempt(page: int, best_path: str, runner_path: str, best_color: float = 0.6, runner_color: float = 0.8):
    best = {
        "path": best_path,
        "page_to_page_hist_drift": 0.02,
        "metadata": {
            "color_score": {"composite_score": best_color},
            "visual_ensemble": {"ensemble_score": 0.65},
            "page_architecture_score": {"composite_score": 0.62},
        },
    }
    runner = {
        "path": runner_path,
        "page_to_page_hist_drift": 0.08,
        "metadata": {
            "color_score": {"composite_score": runner_color},
            "visual_ensemble": {"ensemble_score": 0.82},
            "page_architecture_score": {"composite_score": 0.81},
        },
    }
    return {"page": page, "attempt": 1, "best": best, "variants": [best, runner], "passes": True}


def _sequence_report():
    return {
        "overall_sequence_score": 0.71,
        "weak_clusters": [{"severity": "warning", "pages": [1]}],
        "per_page_notes": [{"page": 1, "premium_qc_score": 0.7, "color_transition_to_page_score": 0.65}],
        "color_transitions": [{"to_page": 1, "expected_mode": "blend", "expected_strength": 0.5}],
    }


def test_noop_when_sequence_report_absent(tmp_path: Path):
    best = tmp_path / "b.png"
    runner = tmp_path / "r.png"
    _img(best, 60)
    _img(runner, 200)
    report = run_bounded_reselection(
        selected=[str(best)],
        qa_attempts=[_qa_attempt(1, str(best), str(runner))],
        sequence_report=None,
    )
    assert not report.enabled
    assert not report.decisions


def test_noop_when_no_better_runner_up(tmp_path: Path):
    best = tmp_path / "b.png"
    runner = tmp_path / "r.png"
    _img(best, 90)
    _img(runner, 100)
    qa = _qa_attempt(1, str(best), str(runner), best_color=0.8, runner_color=0.79)
    qa["variants"][1]["page_to_page_hist_drift"] = 0.0
    qa["variants"][1]["metadata"]["visual_ensemble"]["ensemble_score"] = 0.6
    qa["variants"][1]["metadata"]["page_architecture_score"]["composite_score"] = 0.6
    report = run_bounded_reselection(
        selected=[str(best)],
        qa_attempts=[qa],
        sequence_report=_sequence_report(),
        minimum_required_improvement=0.05,
    )
    assert report.enabled
    assert report.decisions
    assert report.decisions[0].replaced is False


def test_replacement_when_improvement_exists(tmp_path: Path):
    best = tmp_path / "b.png"
    runner = tmp_path / "r.png"
    _img(best, 40)
    _img(runner, 220)
    report = run_bounded_reselection(
        selected=[str(best)],
        qa_attempts=[_qa_attempt(1, str(best), str(runner))],
        sequence_report=_sequence_report(),
        minimum_required_improvement=0.03,
    )
    applied = apply_reselection_decisions([str(best)], report)
    assert applied.replaced_pages == [1]
    assert applied.decisions[0].replaced is True


def test_replacement_cap_enforced(tmp_path: Path):
    imgs = []
    qa = []
    for p in [1, 2]:
        b = tmp_path / f"b{p}.png"
        r = tmp_path / f"r{p}.png"
        _img(b, 50)
        _img(r, 200)
        imgs.append(str(b))
        qa.append(_qa_attempt(p, str(b), str(r)))
    seq = {
        "overall_sequence_score": 0.6,
        "weak_clusters": [{"severity": "warning", "pages": [1, 2]}],
        "per_page_notes": [],
        "color_transitions": [],
    }
    report = run_bounded_reselection(selected=imgs, qa_attempts=qa, sequence_report=seq, max_reselections_per_run=1)
    assert report.replacement_cap_hit
    assert len(report.replaced_pages) == 1


def test_report_schema_and_safe_artifact_generation(tmp_path: Path):
    out = tmp_path / "review" / "reselection_report.json"
    report = run_bounded_reselection(selected=[], qa_attempts=[], sequence_report=None)
    report = with_sequence_improvement(report, before_score=None, after_score=None, re_evaluated=False)
    write_reselection_report(out, report)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "config" in payload
    assert "decisions" in payload
    assert "sequence_improvement" in payload


def test_pipeline_artifact_generation_requirements_include_reselection_report():
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/reselection_report.json" in required
