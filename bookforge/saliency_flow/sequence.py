from __future__ import annotations

from typing import Any, Dict, List

from bookforge.saliency_flow.types import SaliencySequenceFinding


def _run_ranges(pages: List[int], min_len: int = 2) -> List[str]:
    if not pages:
        return []
    pages = sorted(set(pages))
    out: List[str] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        if prev - start + 1 >= min_len:
            out.append(f"Pages {start}-{prev}")
        start = prev = p
    if prev - start + 1 >= min_len:
        out.append(f"Pages {start}-{prev}")
    return out


def build_saliency_sequence_finding(
    page_count: int,
    qa_attempts: List[Dict[str, Any]] | None,
    camera_sequence_plan: Dict[int, Dict[str, Any]] | None,
) -> SaliencySequenceFinding:
    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []
    camera_sequence_plan = camera_sequence_plan if isinstance(camera_sequence_plan, dict) else {}

    by_page: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        page = row.get("page")
        if isinstance(page, int):
            best = row.get("best", {}) if isinstance(row.get("best", {}), dict) else {}
            by_page[page] = best

    weak_fix_pages: List[int] = []
    busy_text_pages: List[int] = []
    turn_resist_pages: List[int] = []
    bridge_fail_pages: List[int] = []
    over_center_pages: List[int] = []
    mismatch: List[str] = []
    positives: List[str] = []

    for p in range(1, page_count + 1):
        best = by_page.get(p, {})
        meta = best.get("metadata", {}) if isinstance(best.get("metadata", {}), dict) else {}
        sf = meta.get("saliency_flow_score", {}) if isinstance(meta.get("saliency_flow_score", {}), dict) else {}
        if not sf:
            continue

        if float(sf.get("primary_focus_score", 1.0) or 1.0) < 0.45:
            weak_fix_pages.append(p)
        if float(sf.get("text_quietness_score", 1.0) or 1.0) < 0.45:
            busy_text_pages.append(p)
        if float(sf.get("page_turn_flow_score", 1.0) or 1.0) < 0.42:
            turn_resist_pages.append(p)
        if float(sf.get("spread_bridge_score", 1.0) or 1.0) < 0.4:
            bridge_fail_pages.append(p)

        peak = (sf.get("peak_summaries") or [{}])[0] if isinstance(sf.get("peak_summaries", []), list) and sf.get("peak_summaries") else {}
        if abs(float(peak.get("x", 0.5) or 0.5) - 0.5) < 0.09 and abs(float(peak.get("y", 0.5) or 0.5) - 0.5) < 0.09:
            over_center_pages.append(p)

        shot = str((camera_sequence_plan.get(p) or {}).get("shot_type", ""))
        if shot == "closeup_emotion" and float(sf.get("text_quietness_score", 1.0) or 1.0) < 0.42:
            mismatch.append(f"Page {p} closeup_emotion has visually busy text zone competing with focus.")
        if shot == "establishing_wide" and float(sf.get("primary_focus_score", 1.0) or 1.0) < 0.48:
            mismatch.append(f"Page {p} establishing_wide lacks a clear first fixation anchor.")

        if float(sf.get("composite_score", 0.0) or 0.0) > 0.72 and p >= int(page_count * 0.6):
            positives.append(f"Page {p} shows strong late-sequence saliency flow support.")

    weak_runs = _run_ranges(weak_fix_pages)
    busy_runs = _run_ranges(busy_text_pages)
    turn_runs = _run_ranges(turn_resist_pages)
    center_runs = _run_ranges(over_center_pages, min_len=3)

    penalties = 0.1 * len(weak_runs) + 0.08 * len(busy_runs) + 0.08 * len(turn_runs) + 0.08 * len(bridge_fail_pages) + 0.05 * len(center_runs) + 0.07 * len(mismatch)
    summary = max(0.0, min(1.0, 1.0 - penalties))

    return SaliencySequenceFinding(
        summary_score=round(summary, 4),
        weak_first_fixation_runs=weak_runs,
        text_busyness_runs=busy_runs,
        page_turn_resistance_runs=turn_runs,
        spread_bridge_failures=[f"Page {p}" for p in sorted(set(bridge_fail_pages))],
        over_centralized_saliency_runs=center_runs,
        camera_mismatch_warnings=mismatch,
        positive_flow_notes=positives[:4],
    )
