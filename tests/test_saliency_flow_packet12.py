from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.qc.image_qc import choose_best_variant
from bookforge.review.book_sequence import build_book_sequence_report
from bookforge.saliency_flow.saliency import analyze_saliency_flow, extract_top_peaks
from bookforge.saliency_flow.scoring import score_page_turn_flow, score_saliency_flow, score_spread_bridge
from bookforge.saliency_flow.text_zones import score_text_zone_quietness


def _qa_cfg() -> dict:
    return {
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
    }


def _img(path: Path, right_bright: bool = False) -> None:
    arr = np.zeros((120, 120, 3), dtype=np.uint8)
    if right_bright:
        arr[:, 85:115, :] = 255
    else:
        arr[:, 5:35, :] = 255
    Image.fromarray(arr, mode="RGB").save(path)


def test_saliency_map_and_peaks_sanity(tmp_path: Path):
    img = tmp_path / "a.png"
    _img(img, right_bright=True)
    sal, flow = analyze_saliency_flow(img)
    assert sal.shape == (120, 120)
    assert 0.0 <= float(sal.min()) <= float(sal.max()) <= 1.0
    assert flow.peaks
    assert flow.first_fixation is not None


def test_peak_extraction_returns_top3_ordered():
    arr = np.zeros((40, 40), dtype=np.float32)
    arr[2, 2] = 1.0
    arr[10, 30] = 0.8
    arr[30, 20] = 0.7
    peaks = extract_top_peaks(arr, top_k=3, min_separation_px=1)
    assert len(peaks) == 3
    assert peaks[0].strength >= peaks[1].strength >= peaks[2].strength


def test_text_zone_quietness_behavior():
    busy = np.zeros((50, 50), dtype=np.float32)
    busy[:, :20] = 0.9
    calm = np.zeros((50, 50), dtype=np.float32)
    zones = [{"zone_type": "text", "x": 0.0, "y": 0.0, "w": 0.4, "h": 1.0}]
    q_busy = score_text_zone_quietness(busy, zones)
    q_calm = score_text_zone_quietness(calm, zones)
    assert q_calm.quietness_score > q_busy.quietness_score


def test_page_turn_direction_scoring_prefers_rightward():
    good = score_page_turn_flow(3, {"rightward_bias": 0.8, "leftward_bias": 0.2}, None)
    bad = score_page_turn_flow(3, {"rightward_bias": 0.2, "leftward_bias": 0.8}, None)
    assert good.page_turn_flow_score > bad.page_turn_flow_score


def test_spread_bridge_scoring():
    map_bridge = np.zeros((60, 120), dtype=np.float32)
    map_bridge[:, :10] = 0.6
    map_bridge[:, -10:] = 0.6
    map_bridge[:, 56:64] = 0.55
    map_dead = np.zeros((60, 120), dtype=np.float32)
    map_dead[:, :10] = 0.6
    map_dead[:, -10:] = 0.6

    good = score_spread_bridge(map_bridge, {"architecture_type": "wordless_spread"})
    bad = score_spread_bridge(map_dead, {"architecture_type": "wordless_spread"})
    assert good.bridge_score > bad.bridge_score


def test_candidate_metadata_attachment_and_disable_flag(tmp_path: Path, monkeypatch):
    img = tmp_path / "img.png"
    style = tmp_path / "style.png"
    _img(img, right_bright=True)
    _img(style, right_bright=True)

    _, qa = choose_best_variant([img], _qa_cfg(), style, None, page_number=1)
    assert "saliency_flow_score" in qa["variants"][0]["metadata"]

    monkeypatch.setenv("BOOKFORGE_SALIENCY_FLOW", "false")
    _, qa_off = choose_best_variant([img], _qa_cfg(), style, None, page_number=1)
    assert "saliency_flow_score" not in qa_off["variants"][0].get("metadata", {})
    monkeypatch.delenv("BOOKFORGE_SALIENCY_FLOW", raising=False)


def test_sequence_report_saliency_artifact_and_noop_when_missing_inputs(tmp_path: Path):
    report = build_book_sequence_report(
        page_count=3,
        color_script={},
        architecture_plan=[],
        applied_arch_rows=[],
        qa_attempts=[],
        premium_qc={},
        camera_sequence_plan={},
    )
    assert hasattr(report, "saliency_flow_sequence")
    assert report.saliency_flow_sequence.summary_score <= 1.0
    assert report.warnings


def test_score_saliency_flow_handles_missing_planning_context(tmp_path: Path):
    img = tmp_path / "b.png"
    _img(img, right_bright=False)
    score = score_saliency_flow(img)
    assert 0.0 <= score.composite_score <= 1.0
    assert score.peak_summaries
