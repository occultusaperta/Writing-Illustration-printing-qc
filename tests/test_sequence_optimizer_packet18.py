from __future__ import annotations

import json

from PIL import Image

from bookforge.pipeline import BookforgePipeline
from bookforge.sequence_optimizer import (
    apply_sequence_optimization_decisions,
    run_sequence_optimization,
    write_sequence_optimization_report,
)


def _make_img(path, c):
    Image.new("RGB", (32, 32), c).save(path)


def _variant(path: str, *, color=0.8, ensemble=0.8, arch=0.8, sal=0.8, shot=0.8, hidden=0.8, char=0.8, drift=0.2, overlap=0.08):
    return {
        "path": path,
        "page_to_page_hist_drift": drift,
        "focus_bleed_overlap": overlap,
        "metadata": {
            "color_score": {"composite_score": color},
            "visual_ensemble": {"ensemble_score": ensemble},
            "page_architecture_score": {"composite_score": arch},
            "saliency_flow_score": {"composite_score": sal},
            "shot_adherence_score": {"composite_score": shot},
            "hidden_world_score": {"composite_score": hidden},
            "character_commercial_score": {"composite_score": char},
        },
    }


def _sequence_report():
    return {
        "overall_sequence_score": 0.62,
        "color_flow_summary_score": 0.58,
        "architecture_flow_summary_score": 0.6,
        "weak_clusters": [{"severity": "warning", "pages": [3, 4]}],
        "color_transitions": [{"to_page": 3, "expected_mode": "blend", "expected_strength": 0.6}],
        "camera_sequence": {"summary_score": 0.61},
        "saliency_flow_sequence": {"summary_score": 0.57},
        "typography_sequence": {"summary_score": 0.54},
        "hidden_world_sequence": {"summary_score": 0.52},
        "character_commercial_summary": {"summary_score": 0.59},
        "layout_search_summary": {"summary_score": 0.56},
        "per_page_notes": [{"page": 3, "premium_qc_score": 0.74}],
    }


def test_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "false")
    r = run_sequence_optimization(selected=["a", "b"], qa_attempts=[], sequence_report=_sequence_report())
    assert r.enabled is False
    assert r.candidate_moves_considered == 0


def test_noop_when_no_runner_up_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    qa = [{"page": 1, "attempt": 1, "best": _variant("/tmp/a.png"), "variants": [_variant("/tmp/a.png")]}]
    r = run_sequence_optimization(selected=["/tmp/a.png"], qa_attempts=qa, sequence_report=_sequence_report())
    assert r.enabled is True
    assert r.candidate_moves_considered == 0
    assert r.warnings


def test_accept_move_above_threshold_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT", "0.01")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION", "0")
    qa = [
        {
            "page": 3,
            "attempt": 1,
            "best": _variant("/x/current.png", color=0.62, ensemble=0.62, arch=0.58, sal=0.56, shot=0.56, drift=0.45, overlap=0.2),
            "variants": [
                _variant("/x/current.png", color=0.62, ensemble=0.62, arch=0.58, sal=0.56, shot=0.56, drift=0.45, overlap=0.2),
                _variant("/x/up1.png", color=0.82, ensemble=0.85, arch=0.79, sal=0.78, shot=0.75, drift=0.2, overlap=0.05),
            ],
        }
    ]
    r1 = run_sequence_optimization(selected=["a", "b", "/x/current.png", "d"], qa_attempts=qa, sequence_report=_sequence_report())
    r2 = run_sequence_optimization(selected=["a", "b", "/x/current.png", "d"], qa_attempts=qa, sequence_report=_sequence_report())
    assert [m.candidate.runner_up_candidate_path for m in r1.accepted_moves] == [m.candidate.runner_up_candidate_path for m in r2.accepted_moves]
    assert r1.accepted_moves


def test_reject_move_on_local_regression(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT", "0.0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_LOCAL_REGRESSION", "0.001")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION", "0")
    qa = [{"page": 3, "attempt": 1, "best": _variant("/x/current.png", color=0.8), "variants": [_variant("/x/current.png", color=0.8), _variant("/x/down.png", color=0.4)]}]
    r = run_sequence_optimization(selected=["a", "b", "/x/current.png", "d"], qa_attempts=qa, sequence_report=_sequence_report())
    assert not r.accepted_moves
    assert r.rejected_moves


def test_move_cap_and_protection(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_MOVES", "1")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT", "0.01")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION", "1")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION", "1")
    qa = []
    for p in [1, 2, 3, 4]:
        qa.append(
            {
                "page": p,
                "attempt": 1,
                "best": _variant(f"/x/{p}_c.png", color=0.55, ensemble=0.55, arch=0.55, sal=0.55),
                "variants": [
                    _variant(f"/x/{p}_c.png", color=0.55, ensemble=0.55, arch=0.55, sal=0.55),
                    _variant(f"/x/{p}_u.png", color=0.85, ensemble=0.85, arch=0.85, sal=0.85),
                ],
            }
        )
    r = run_sequence_optimization(selected=["1", "2", "3", "4"], qa_attempts=qa, sequence_report=_sequence_report())
    assert len(r.accepted_moves) <= 1
    assert all(m.page not in {1, 4} for m in r.accepted_moves)


def test_apply_and_report_schema_and_verify_expectations(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZATION", "true")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT", "0.01")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION", "0")
    monkeypatch.setenv("BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION", "0")
    cur = tmp_path / "p3.png"
    alt = tmp_path / "p3_alt.png"
    _make_img(cur, (20, 20, 20))
    _make_img(alt, (220, 220, 220))
    qa = [{"page": 3, "attempt": 1, "best": _variant(str(cur), color=0.5, ensemble=0.5, arch=0.5, sal=0.5, drift=0.42), "variants": [_variant(str(cur), color=0.5, ensemble=0.5, arch=0.5, sal=0.5, drift=0.42), _variant(str(alt), color=0.9, ensemble=0.9, arch=0.9, sal=0.9, drift=0.2)]}]
    selected = [str(cur), str(cur), str(cur)]
    rep = run_sequence_optimization(selected=selected, qa_attempts=qa, sequence_report=_sequence_report())
    rep = apply_sequence_optimization_decisions(selected=selected, qa_attempts=qa, report=rep)
    out = tmp_path / "review" / "sequence_optimization_report.json"
    write_sequence_optimization_report(out, rep)
    payload = json.loads(out.read_text(encoding="utf-8"))
    for k in ["enabled", "config", "pages_considered", "candidate_moves_considered", "accepted_moves", "rejected_moves", "cap_hit", "before_summary", "after_summary", "net_improvement"]:
        assert k in payload

    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/sequence_optimization_report.json" in required
