from __future__ import annotations

import json

from bookforge.pipeline import BookforgePipeline
from bookforge.review.book_sequence import build_book_sequence_report, write_book_sequence_report


def _base_color_script():
    return {
        "pages": [
            {"page_number": 1, "target_lightness": 55, "forbidden_colors_lab": [[10, 0, 0]]},
            {"page_number": 2, "target_lightness": 56, "forbidden_colors_lab": [[10, 0, 0]]},
            {"page_number": 3, "target_lightness": 57, "forbidden_colors_lab": [[10, 0, 0]]},
            {"page_number": 4, "target_lightness": 58, "forbidden_colors_lab": [[10, 0, 0]]},
        ],
        "transitions": [
            {"from_page": 1, "to_page": 2, "mode": "blend", "strength": 0.5},
            {"from_page": 2, "to_page": 3, "mode": "hard_cut", "strength": 0.8},
            {"from_page": 3, "to_page": 4, "mode": "blend", "strength": 0.4},
        ],
    }


def test_color_transition_report_generation():
    qa_attempts = [
        {"page": 2, "best": {"page_to_page_hist_drift": 0.10, "forbidden_penalty": 0.0}},
        {"page": 3, "best": {"page_to_page_hist_drift": 0.09, "forbidden_penalty": 0.4}},
        {"page": 4, "best": {"page_to_page_hist_drift": 0.11, "forbidden_penalty": 0.35}},
    ]
    report = build_book_sequence_report(
        page_count=4,
        color_script=_base_color_script(),
        architecture_plan=[],
        applied_arch_rows=[],
        qa_attempts=qa_attempts,
        premium_qc={"pages": []},
    )
    assert len(report.color_transitions) == 3
    hard_cut = [f for f in report.color_transitions if f.expected_mode == "hard_cut"][0]
    assert any("Missing contrast" in w for w in hard_cut.warnings)
    assert any("contamination cluster" in n.lower() for n in report.summary_notes)


def test_architecture_repetition_detection():
    architecture_plan = [
        {"page_number": 1, "target_energy": 0.4, "selected_architecture_type": "text_dominant"},
        {"page_number": 2, "target_energy": 0.45, "selected_architecture_type": "text_dominant"},
        {"page_number": 3, "target_energy": 0.46, "selected_architecture_type": "text_dominant"},
        {"page_number": 4, "target_energy": 0.5, "selected_architecture_type": "vignette"},
    ]
    applied = [
        {"page": 1, "architecture_type": "text_dominant"},
        {"page": 2, "architecture_type": "text_dominant"},
        {"page": 3, "architecture_type": "text_dominant"},
        {"page": 4, "architecture_type": "vignette"},
    ]
    report = build_book_sequence_report(
        page_count=4,
        color_script={},
        architecture_plan=architecture_plan,
        applied_arch_rows=applied,
        qa_attempts=[],
        premium_qc={"pages": []},
    )
    assert report.architecture_flow.repeated_pattern_warnings
    assert report.architecture_flow.text_heavy_cluster_warnings


def test_energy_curve_mismatch_detection():
    architecture_plan = [
        {"page_number": 1, "target_energy": 0.2, "selected_architecture_type": "spot_illustration"},
        {"page_number": 2, "target_energy": 0.9, "selected_architecture_type": "wordless_spread"},
        {"page_number": 3, "target_energy": 0.3, "selected_architecture_type": "vignette"},
    ]
    applied = [
        {"page": 1, "architecture_type": "text_dominant"},
        {"page": 2, "architecture_type": "vignette"},
        {"page": 3, "architecture_type": "full_bleed_spread"},
    ]
    premium = {
        "pages": [
            {"page": 1, "score": 0.95, "visual_critic_scores": {"composition_score": 0.9}},
            {"page": 2, "score": 0.95, "visual_critic_scores": {"composition_score": 0.85}},
            {"page": 3, "score": 0.95, "visual_critic_scores": {"composition_score": 0.9}},
        ]
    }
    report = build_book_sequence_report(
        page_count=3,
        color_script={},
        architecture_plan=architecture_plan,
        applied_arch_rows=applied,
        qa_attempts=[],
        premium_qc=premium,
    )
    assert report.energy_curve.mismatch_score < 0.8


def test_weak_cluster_detection():
    architecture_plan = [{"page_number": i, "target_energy": 0.4, "selected_architecture_type": "text_dominant"} for i in range(1, 6)]
    applied = [{"page": i, "architecture_type": "text_dominant"} for i in range(1, 6)]
    premium = {"pages": [{"page": i, "score": 0.7, "visual_critic_scores": {"composition_score": 0.5}} for i in range(1, 6)]}
    color_script = {
        "pages": [{"page_number": i, "target_lightness": 56, "forbidden_colors_lab": []} for i in range(1, 6)],
        "transitions": [{"from_page": i, "to_page": i + 1, "mode": "blend", "strength": 0.4} for i in range(1, 5)],
    }
    qa_attempts = [{"page": i + 1, "best": {"page_to_page_hist_drift": 0.02}} for i in range(1, 5)]
    report = build_book_sequence_report(
        page_count=5,
        color_script=color_script,
        architecture_plan=architecture_plan,
        applied_arch_rows=applied,
        qa_attempts=qa_attempts,
        premium_qc=premium,
    )
    assert report.weak_clusters
    assert any("visually repetitive" in c.reason for c in report.weak_clusters)


def test_report_schema_and_safe_behavior_when_metadata_absent(tmp_path):
    report = build_book_sequence_report(
        page_count=3,
        color_script=None,
        architecture_plan=None,
        applied_arch_rows=None,
        qa_attempts=None,
        premium_qc=None,
    )
    out = tmp_path / "review" / "book_sequence_report.json"
    write_book_sequence_report(out, report)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "overall_sequence_score" in payload
    assert "color_transitions" in payload
    assert "weak_clusters" in payload
    assert report.warnings


def test_pipeline_artifact_generation_requirements_include_sequence_report():
    required = BookforgePipeline()._expected_package_artifacts()
    assert "review/book_sequence_report.json" in required
