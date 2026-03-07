from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from bookforge.hidden_world.types import HiddenWorldSequenceFinding
from bookforge.utils import clamp01


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


def build_hidden_world_sequence_finding(
    *,
    page_count: int,
    hidden_world_plan: Dict[str, Any] | None,
    qa_attempts: List[Dict[str, Any]] | None,
) -> HiddenWorldSequenceFinding:
    hidden_world_plan = hidden_world_plan if isinstance(hidden_world_plan, dict) else {}
    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []

    detail_plans = hidden_world_plan.get("detail_plans", []) if isinstance(hidden_world_plan.get("detail_plans", []), list) else []
    recurring_motifs = hidden_world_plan.get("recurring_motifs", []) if isinstance(hidden_world_plan.get("recurring_motifs", []), list) else []

    hidden_scores: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        p = row.get("page")
        best = row.get("best", {}) if isinstance(row.get("best", {}), dict) else {}
        meta = best.get("metadata", {}) if isinstance(best.get("metadata", {}), dict) else {}
        hs = meta.get("hidden_world_score", {}) if isinstance(meta.get("hidden_world_score", {}), dict) else {}
        if isinstance(p, int) and hs:
            hidden_scores[p] = hs

    low_recurrence_pages: List[int] = []
    too_dominant_pages: List[int] = []
    too_invisible_pages: List[int] = []
    over_obvious: List[str] = []
    parent_notes: List[str] = []
    foreshadow_notes: List[str] = []
    positives: List[str] = []
    warnings: List[str] = []

    for p in range(1, page_count + 1):
        hs = hidden_scores.get(p, {})
        if not hs:
            continue
        rec = float(hs.get("recurrence_consistency_score", 0.5) or 0.5)
        subtle = float(hs.get("subtlety_score", 0.5) or 0.5)
        parent = float(hs.get("parent_reward_score", 0.5) or 0.5)
        if rec < 0.45:
            low_recurrence_pages.append(p)
        if subtle < 0.35:
            too_dominant_pages.append(p)
            over_obvious.append(f"Page {p} hidden details may read too obvious/dominant.")
        if subtle > 0.92 and float(hs.get("required_detail_presence_score", 0.5) or 0.5) < 0.75:
            too_invisible_pages.append(p)
        if parent > 0.68:
            parent_notes.append(f"Page {p} has strong parent-reward environmental detail cues.")
        if float(hs.get("foreshadowing_callback_score", 0.5) or 0.5) > 0.66:
            foreshadow_notes.append(f"Page {p} contributes to foreshadow/callback chain continuity.")
        if float(hs.get("composite_score", 0.0) or 0.0) > 0.75:
            positives.append(f"Page {p} supports rereadability with balanced hidden-world cues.")

    motif_notes: List[str] = []
    for detail in detail_plans:
        if not isinstance(detail, dict):
            continue
        if detail.get("detail_type") == "recurring_motif":
            pages = detail.get("page_numbers", []) if isinstance(detail.get("page_numbers", []), list) else []
            if len(pages) >= 2:
                motif_notes.append(f"Motif '{detail.get('detail_text', '')}' recurs on {len(pages)} pages.")
            else:
                warnings.append(f"Motif '{detail.get('detail_text', '')}' lacks recurrence depth.")

    if recurring_motifs and not motif_notes:
        motif_notes.append("Recurring motif inventory exists but continuity evidence is limited.")

    weak_runs = _run_ranges(low_recurrence_pages)
    invisible_runs = _run_ranges(too_invisible_pages)
    dominant_runs = _run_ranges(too_dominant_pages)

    penalties = 0.09 * len(weak_runs) + 0.07 * len(too_dominant_pages) + 0.07 * len(too_invisible_pages) + 0.06 * len(warnings)
    summary_score = clamp01(1.0 - penalties)

    return HiddenWorldSequenceFinding(
        summary_score=round(summary_score, 4),
        recurring_motif_continuity_notes=motif_notes,
        weak_recurrence_stretches=weak_runs,
        over_obvious_warnings=over_obvious,
        too_dominant_warnings=[f"Page {p} hidden detail saliency likely too dominant." for p in too_dominant_pages],
        likely_too_invisible_warnings=[f"Page {p} hidden details may be too subtle to detect." for p in too_invisible_pages],
        foreshadow_callback_notes=foreshadow_notes[:6],
        parent_reward_density_notes=parent_notes[:6],
        positive_rereadability_highlights=positives[:6],
        warnings=warnings,
    )


def write_hidden_world_report(path: Path, finding: HiddenWorldSequenceFinding) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(finding.to_dict(), indent=2), encoding="utf-8")
