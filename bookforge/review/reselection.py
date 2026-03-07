from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from bookforge.scoring_registry import scoring_registry, transition_target
from bookforge.utils import clamp01


@dataclass(frozen=True)
class CandidateComparison:
    page: int
    current_path: str
    candidate_path: str
    current_local_score: float
    candidate_local_score: float
    local_delta: float
    current_sequence_support: float
    candidate_sequence_support: float
    sequence_delta: float
    current_composite_score: float
    candidate_composite_score: float
    composite_delta: float
    accepted: bool
    decision_reason: str


@dataclass(frozen=True)
class ReselectionDecision:
    page: int
    considered: bool
    replaced: bool
    selected_before: str
    selected_after: str
    reason: str
    best_comparison: CandidateComparison | None


@dataclass(frozen=True)
class SequenceImprovementSummary:
    re_evaluated: bool
    before_overall_sequence_score: float | None
    after_overall_sequence_score: float | None
    delta: float | None


@dataclass(frozen=True)
class ReselectionRunReport:
    enabled: bool
    config: Dict[str, Any]
    considered_pages: List[int]
    eligible_pages: List[int]
    replaced_pages: List[int]
    replacement_cap_hit: bool
    decisions: List[ReselectionDecision]
    sequence_improvement: SequenceImprovementSummary
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def write_reselection_report(path: Path, report: ReselectionRunReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def _score_local(candidate: Dict[str, Any]) -> float:
    metadata = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
    color = ((metadata.get("color_score") or {}).get("composite_score", 0.5)) if isinstance(metadata, dict) else 0.5
    ensemble = ((metadata.get("visual_ensemble") or {}).get("ensemble_score", 0.5)) if isinstance(metadata, dict) else 0.5
    arch = ((metadata.get("page_architecture_score") or {}).get("composite_score", 0.5)) if isinstance(metadata, dict) else 0.5
    saliency = ((metadata.get("saliency_flow_score") or {}).get("composite_score", 0.5)) if isinstance(metadata, dict) else 0.5
    weights = scoring_registry().local_candidate.reselection_local_weights
    return round(clamp01(weights["color"] * float(color) + weights["ensemble"] * float(ensemble) + weights["architecture"] * float(arch) + weights["saliency"] * float(saliency)), 6)


def _score_sequence_support(page: int, candidate: Dict[str, Any], sequence_report: Dict[str, Any]) -> float:
    transition_rows = sequence_report.get("color_transitions", []) if isinstance(sequence_report, dict) else []
    transition = next((row for row in transition_rows if int(row.get("to_page", 0)) == page), None)
    drift = float(candidate.get("page_to_page_hist_drift", 0.0) or 0.0)
    if transition:
        target = transition_target(str(transition.get("expected_mode", "blend")), float(transition.get("expected_strength", 0.5) or 0.5))
        transition_fit = clamp01(1.0 - abs(drift - target))
    else:
        transition_fit = 0.5

    metadata = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
    ensemble = float(((metadata.get("visual_ensemble") or {}).get("ensemble_score", 0.5)) or 0.5)
    arch = float(((metadata.get("page_architecture_score") or {}).get("composite_score", 0.5)) or 0.5)

    weights = scoring_registry().local_candidate.reselection_sequence_support_weights
    return round(clamp01(weights["transition_fit"] * transition_fit + weights["ensemble"] * ensemble + weights["architecture"] * arch), 6)


def _sequence_flagged_pages(sequence_report: Dict[str, Any]) -> set[int]:
    flagged: set[int] = set()
    for cluster in sequence_report.get("weak_clusters", []):
        if str(cluster.get("severity", "")).lower() in {"warning", "error"}:
            for p in cluster.get("pages", []):
                if isinstance(p, int):
                    flagged.add(p)
    for row in sequence_report.get("per_page_notes", []):
        if not isinstance(row, dict):
            continue
        page = int(row.get("page", 0) or 0)
        if page <= 0:
            continue
        if float(row.get("premium_qc_score", 1.0) or 1.0) < scoring_registry().thresholds.reselection_premium_qc_min:
            flagged.add(page)
        cscore = row.get("color_transition_to_page_score")
        if cscore is not None and float(cscore) < scoring_registry().thresholds.reselection_transition_score_min:
            flagged.add(page)
    return flagged


def _severe_local_issue(candidate: Dict[str, Any]) -> bool:
    metadata = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
    color = float(((metadata.get("color_score") or {}).get("composite_score", 1.0)) or 1.0)
    ensemble = float(((metadata.get("visual_ensemble") or {}).get("ensemble_score", 1.0)) or 1.0)
    arch = float(((metadata.get("page_architecture_score") or {}).get("composite_score", 1.0)) or 1.0)
    saliency = float(((metadata.get("saliency_flow_score") or {}).get("composite_score", 1.0)) or 1.0)
    thresholds = scoring_registry().thresholds
    return color < thresholds.reselection_color_min or ensemble < thresholds.reselection_ensemble_min or arch < thresholds.reselection_architecture_min or saliency < thresholds.reselection_saliency_min


def _candidate_pool_by_page(qa_attempts: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    pool: Dict[int, Dict[str, Any]] = {}
    for attempt in qa_attempts:
        page = attempt.get("page")
        if not isinstance(page, int):
            continue
        variants = attempt.get("variants", [])
        best = attempt.get("best", {})
        if not isinstance(variants, list) or not isinstance(best, dict):
            continue
        if len(variants) < 2:
            continue
        prev = pool.get(page)
        if prev is None or int(attempt.get("attempt", 0) or 0) >= int(prev.get("attempt", 0) or 0):
            pool[page] = attempt
    return pool


def run_bounded_reselection(
    *,
    selected: List[str],
    qa_attempts: List[Dict[str, Any]],
    sequence_report: Dict[str, Any] | None,
    max_reselections_per_run: int = 2,
    minimum_required_improvement: float = 0.04,
    allow_regeneration: bool = False,
) -> ReselectionRunReport:
    config = {
        "max_reselections_per_run": int(max(0, max_reselections_per_run)),
        "minimum_required_improvement": float(max(0.0, minimum_required_improvement)),
        "allow_regeneration": bool(allow_regeneration),
    }
    notes: List[str] = []
    if not sequence_report:
        notes.append("No sequence report available; reselection is a no-op.")
        return ReselectionRunReport(
            enabled=False,
            config=config,
            considered_pages=[],
            eligible_pages=[],
            replaced_pages=[],
            replacement_cap_hit=False,
            decisions=[],
            sequence_improvement=SequenceImprovementSummary(False, None, None, None),
            notes=notes,
        )

    pools = _candidate_pool_by_page(qa_attempts)
    if not pools:
        notes.append("No runner-up candidate pools available; reselection is a no-op.")

    flagged = _sequence_flagged_pages(sequence_report)
    eligible: List[int] = []
    for page, attempt in sorted(pools.items()):
        best = attempt.get("best", {}) if isinstance(attempt.get("best", {}), dict) else {}
        if page in flagged or _severe_local_issue(best):
            eligible.append(page)

    decisions: List[ReselectionDecision] = []
    replaced: List[int] = []
    considered: List[int] = []

    for page in eligible:
        if len(replaced) >= config["max_reselections_per_run"]:
            break
        attempt = pools[page]
        best = attempt.get("best", {})
        variants = [row for row in attempt.get("variants", []) if isinstance(row, dict)]
        current_path = str(best.get("path", ""))
        runner_ups = [row for row in variants if str(row.get("path", "")) and str(row.get("path", "")) != current_path]
        considered.append(page)
        if not runner_ups:
            decisions.append(
                ReselectionDecision(
                    page=page,
                    considered=True,
                    replaced=False,
                    selected_before=selected[page - 1] if 0 < page <= len(selected) else "",
                    selected_after=selected[page - 1] if 0 < page <= len(selected) else "",
                    reason="No runner-up variants available for comparison.",
                    best_comparison=None,
                )
            )
            continue

        current_local = _score_local(best)
        current_seq = _score_sequence_support(page, best, sequence_report)
        comp_weights = scoring_registry().local_candidate.reselection_composite_weights
        current_comp = clamp01(comp_weights["local"] * current_local + comp_weights["sequence"] * current_seq)

        best_comp: CandidateComparison | None = None
        for candidate in runner_ups:
            cand_local = _score_local(candidate)
            cand_seq = _score_sequence_support(page, candidate, sequence_report)
            cand_comp = clamp01(comp_weights["local"] * cand_local + comp_weights["sequence"] * cand_seq)
            local_delta = round(cand_local - current_local, 6)
            seq_delta = round(cand_seq - current_seq, 6)
            comp_delta = round(cand_comp - current_comp, 6)
            accept = bool(
                comp_delta >= config["minimum_required_improvement"]
                and (local_delta >= config["minimum_required_improvement"] or seq_delta >= config["minimum_required_improvement"])
            )
            reason = "Measurable local/sequence improvement." if accept else "Improvement below threshold."
            comparison = CandidateComparison(
                page=page,
                current_path=current_path,
                candidate_path=str(candidate.get("path", "")),
                current_local_score=current_local,
                candidate_local_score=cand_local,
                local_delta=local_delta,
                current_sequence_support=current_seq,
                candidate_sequence_support=cand_seq,
                sequence_delta=seq_delta,
                current_composite_score=round(current_comp, 6),
                candidate_composite_score=round(cand_comp, 6),
                composite_delta=comp_delta,
                accepted=accept,
                decision_reason=reason,
            )
            if best_comp is None or comparison.composite_delta > best_comp.composite_delta:
                best_comp = comparison

        before = selected[page - 1] if 0 < page <= len(selected) else ""
        after = before
        replaced_now = False
        decision_reason = "No candidate exceeded required improvement threshold."
        if best_comp and best_comp.accepted and 0 < page <= len(selected):
            after = before
            replaced_now = True
            replaced.append(page)
            decision_reason = "Replaced with runner-up that improved bounded composite score."
        decisions.append(
            ReselectionDecision(
                page=page,
                considered=True,
                replaced=replaced_now,
                selected_before=before,
                selected_after=after,
                reason=decision_reason,
                best_comparison=best_comp,
            )
        )

    if not decisions and sequence_report:
        notes.append("No pages met reselection eligibility criteria.")

    return ReselectionRunReport(
        enabled=True,
        config=config,
        considered_pages=considered,
        eligible_pages=eligible,
        replaced_pages=replaced,
        replacement_cap_hit=len(replaced) >= config["max_reselections_per_run"] and len(eligible) > len(replaced),
        decisions=decisions,
        sequence_improvement=SequenceImprovementSummary(False, sequence_report.get("overall_sequence_score"), None, None),
        notes=notes,
    )


def apply_reselection_decisions(selected: List[str], report: ReselectionRunReport) -> ReselectionRunReport:
    """Apply accepted replacements onto selected page outputs in a bounded way."""
    updated_decisions: List[ReselectionDecision] = []
    replaced_pages: List[int] = []
    for decision in report.decisions:
        best = decision.best_comparison
        before = decision.selected_before
        after = before
        replaced = False
        reason = decision.reason
        if decision.replaced and best and best.accepted and 0 < decision.page <= len(selected):
            page_path = Path(selected[decision.page - 1])
            candidate_path = Path(best.candidate_path)
            if page_path.exists() and candidate_path.exists():
                with Image.open(page_path) as base_im, Image.open(candidate_path) as cand_im:
                    base = base_im.convert("RGB")
                    cand = cand_im.convert("RGB")
                    if cand.size != base.size:
                        cand = cand.resize(base.size, Image.Resampling.LANCZOS)
                    cand.save(page_path, "PNG")
                after = str(page_path)
                replaced = True
                replaced_pages.append(decision.page)
                reason = "Replacement applied from runner-up candidate pool."
            else:
                reason = "Replacement candidate missing on disk; kept current selection."

        updated_decisions.append(
            ReselectionDecision(
                page=decision.page,
                considered=decision.considered,
                replaced=replaced,
                selected_before=before,
                selected_after=after,
                reason=reason,
                best_comparison=best,
            )
        )
    return ReselectionRunReport(
        enabled=report.enabled,
        config=report.config,
        considered_pages=report.considered_pages,
        eligible_pages=report.eligible_pages,
        replaced_pages=sorted(replaced_pages),
        replacement_cap_hit=report.replacement_cap_hit,
        decisions=updated_decisions,
        sequence_improvement=report.sequence_improvement,
        notes=report.notes,
    )


def with_sequence_improvement(
    report: ReselectionRunReport,
    *,
    before_score: float | None,
    after_score: float | None,
    re_evaluated: bool,
) -> ReselectionRunReport:
    delta = None
    if before_score is not None and after_score is not None:
        delta = round(float(after_score) - float(before_score), 6)
    return ReselectionRunReport(
        enabled=report.enabled,
        config=report.config,
        considered_pages=report.considered_pages,
        eligible_pages=report.eligible_pages,
        replaced_pages=report.replaced_pages,
        replacement_cap_hit=report.replacement_cap_hit,
        decisions=report.decisions,
        sequence_improvement=SequenceImprovementSummary(re_evaluated, before_score, after_score, delta),
        notes=report.notes,
    )
