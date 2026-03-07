from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from bookforge.review.reselection import _score_local, _score_sequence_support
from bookforge.utils import clamp01


@dataclass(frozen=True)
class RegenerationCandidateRequest:
    page: int
    target: str
    reason: str
    prompt: str
    negative_prompt: str
    prompt_delta: str
    lock_context: Dict[str, Any]
    planning_context: Dict[str, Any]
    weak_dimensions: List[str]
    variants_per_regeneration: int


@dataclass(frozen=True)
class RegenerationComparison:
    page: int
    previous_path: str
    candidate_path: str
    previous_local_score: float
    candidate_local_score: float
    local_delta: float
    previous_sequence_support: float
    candidate_sequence_support: float
    sequence_delta: float
    previous_composite_score: float
    candidate_composite_score: float
    composite_delta: float
    accepted: bool
    reason: str


@dataclass(frozen=True)
class RegenerationDecision:
    page: int
    target: str
    eligible: bool
    regenerated: bool
    replaced: bool
    reason: str
    request: RegenerationCandidateRequest | None
    comparison: RegenerationComparison | None


@dataclass(frozen=True)
class RegenerationImprovementSummary:
    sequence_re_evaluated: bool
    before_overall_sequence_score: float | None
    after_overall_sequence_score: float | None
    sequence_delta: float | None


@dataclass(frozen=True)
class RegenerationRunReport:
    enabled: bool
    config: Dict[str, Any]
    provider_available: bool
    eligible_targets: List[str]
    regenerated_targets: List[str]
    replaced_targets: List[str]
    replacement_cap_hit: bool
    decisions: List[RegenerationDecision]
    sequence_improvement: RegenerationImprovementSummary
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def write_targeted_regeneration_report(path: Path, report: RegenerationRunReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def _weak_dimensions(candidate: Dict[str, Any]) -> List[str]:
    metadata = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
    dims: List[str] = []
    if float(((metadata.get("color_score") or {}).get("composite_score", 1.0)) or 1.0) < 0.68:
        dims.append("color")
    if float(((metadata.get("visual_ensemble") or {}).get("ensemble_score", 1.0)) or 1.0) < 0.70:
        dims.append("visual_ensemble")
    if float(((metadata.get("page_architecture_score") or {}).get("composite_score", 1.0)) or 1.0) < 0.65:
        dims.append("architecture")
    if float(((metadata.get("saliency_flow_score") or {}).get("composite_score", 1.0)) or 1.0) < 0.45:
        dims.append("saliency_flow")
    overlap = float(candidate.get("focus_bleed_overlap", 0.0) or 0.0)
    if overlap > 0.16:
        dims.append("layout_conflict")
    return dims


def _is_sequence_flagged(page: int, sequence_report: Dict[str, Any]) -> bool:
    for cluster in sequence_report.get("weak_clusters", []):
        if not isinstance(cluster, dict):
            continue
        if str(cluster.get("severity", "")).lower() in {"warning", "error"} and page in cluster.get("pages", []):
            return True
    for row in sequence_report.get("per_page_notes", []):
        if not isinstance(row, dict):
            continue
        if int(row.get("page", 0) or 0) != page:
            continue
        if float(row.get("premium_qc_score", 1.0) or 1.0) < 0.76:
            return True
        score = row.get("color_transition_to_page_score")
        if score is not None and float(score) < 0.70:
            return True
    return False


def run_targeted_regeneration(
    *,
    selected: List[str],
    prompts: List[Dict[str, Any]],
    qa_attempts: List[Dict[str, Any]],
    sequence_report: Dict[str, Any] | None,
    reselection_report: Dict[str, Any] | None,
    planning_prompt_guidance: Dict[int, Dict[str, Any]] | None,
    lock_context: Dict[str, Any],
    provider_available: bool,
    max_regenerations_per_run: int = 1,
    minimum_required_improvement: float = 0.05,
    variants_per_regeneration: int = 1,
    allow_spread_regeneration: bool = False,
) -> RegenerationRunReport:
    config = {
        "max_regenerations_per_run": int(max(0, max_regenerations_per_run)),
        "minimum_required_improvement": float(max(0.0, minimum_required_improvement)),
        "variants_per_regeneration": int(max(1, variants_per_regeneration)),
        "allow_spread_regeneration": bool(allow_spread_regeneration),
    }
    notes: List[str] = []
    if not sequence_report:
        notes.append("Sequence report unavailable; targeted regeneration is a no-op.")
        return RegenerationRunReport(False, config, provider_available, [], [], [], False, [], RegenerationImprovementSummary(False, None, None, None), notes)
    if not provider_available:
        notes.append("Runtime/provider unavailable; targeted regeneration is a no-op.")
        return RegenerationRunReport(True, config, provider_available, [], [], [], False, [], RegenerationImprovementSummary(False, float(sequence_report.get("overall_sequence_score", 0.0)), None, None), notes)

    prompt_by_page = {
        int(item.get("page_number", 0)): str(item.get("prompt", ""))
        for item in prompts
        if isinstance(item, dict) and int(item.get("page_number", 0) or 0) > 0
    }
    qa_latest_by_page: Dict[int, Dict[str, Any]] = {}
    for attempt in qa_attempts:
        page = attempt.get("page")
        if not isinstance(page, int):
            continue
        prev = qa_latest_by_page.get(page)
        if prev is None or int(attempt.get("attempt", 0) or 0) >= int(prev.get("attempt", 0) or 0):
            qa_latest_by_page[page] = attempt

    unresolved_pages = {
        int(d.get("page"))
        for d in (reselection_report or {}).get("decisions", [])
        if isinstance(d, dict) and int(d.get("page", 0) or 0) > 0 and not bool(d.get("replaced", False))
    }
    eligible_pages: List[int] = []
    reasons: Dict[int, str] = {}
    for page, attempt in sorted(qa_latest_by_page.items()):
        best = attempt.get("best", {}) if isinstance(attempt.get("best", {}), dict) else {}
        weak_dims = _weak_dimensions(best)
        local_issue = bool(weak_dims)
        flagged = _is_sequence_flagged(page, sequence_report)
        unresolved = page in unresolved_pages
        if flagged or unresolved or local_issue:
            eligible_pages.append(page)
            reason_bits: List[str] = []
            if flagged:
                reason_bits.append("flagged_weak_cluster")
            if unresolved:
                reason_bits.append("unresolved_after_reselection")
            if local_issue:
                reason_bits.append("severe_local_issue:" + ",".join(weak_dims))
            reasons[page] = "; ".join(reason_bits)

    if not eligible_pages:
        notes.append("No weak pages/spreads met targeted regeneration eligibility rules.")
        return RegenerationRunReport(True, config, provider_available, [], [], [], False, [], RegenerationImprovementSummary(False, float(sequence_report.get("overall_sequence_score", 0.0)), None, None), notes)

    decisions: List[RegenerationDecision] = []
    regenerated_targets: List[str] = []
    replaced_targets: List[str] = []

    for page in eligible_pages:
        if len(regenerated_targets) >= config["max_regenerations_per_run"]:
            break
        attempt = qa_latest_by_page.get(page, {})
        best = attempt.get("best", {}) if isinstance(attempt.get("best", {}), dict) else {}
        if not isinstance(best, dict) or not best.get("path"):
            decisions.append(RegenerationDecision(page, f"page:{page}", True, False, False, "Missing best candidate metadata.", None, None))
            continue
        weak_dims = _weak_dimensions(best)
        prompt_delta = ""
        if "layout_conflict" in weak_dims:
            prompt_delta += " subject centered in quiet-zone safe area with gutter safety;"
        if "color" in weak_dims:
            prompt_delta += " enforce palette adherence from approved style tile;"
        if "architecture" in weak_dims:
            prompt_delta += " respect planned page architecture framing and text-safe composition;"
        if "visual_ensemble" in weak_dims:
            prompt_delta += " increase clarity/composition coherence and reduce clutter;"
        prompt_delta = prompt_delta.strip(" ;") or "small bounded refinement preserving existing lock identity"
        request = RegenerationCandidateRequest(
            page=page,
            target=f"page:{page}",
            reason=reasons.get(page, "weak_page"),
            prompt=prompt_by_page.get(page, ""),
            negative_prompt=str(lock_context.get("negative_prompt", "")),
            prompt_delta=prompt_delta,
            lock_context=lock_context,
            planning_context=(planning_prompt_guidance or {}).get(page, {}),
            weak_dimensions=weak_dims,
            variants_per_regeneration=config["variants_per_regeneration"],
        )
        decisions.append(RegenerationDecision(page, f"page:{page}", True, True, False, "Eligible for bounded targeted regeneration.", request, None))
        regenerated_targets.append(f"page:{page}")

    return RegenerationRunReport(
        enabled=True,
        config=config,
        provider_available=provider_available,
        eligible_targets=[f"page:{p}" for p in eligible_pages],
        regenerated_targets=regenerated_targets,
        replaced_targets=replaced_targets,
        replacement_cap_hit=(config["max_regenerations_per_run"] > 0 and len(regenerated_targets) >= config["max_regenerations_per_run"] and len(eligible_pages) > len(regenerated_targets)),
        decisions=decisions,
        sequence_improvement=RegenerationImprovementSummary(False, float(sequence_report.get("overall_sequence_score", 0.0)), None, None),
        notes=notes,
    )


def apply_targeted_regeneration_decisions(
    *,
    selected: List[str],
    report: RegenerationRunReport,
    sequence_report: Dict[str, Any],
    previous_candidates: Dict[int, Dict[str, Any]],
    generated_candidates: Dict[int, Dict[str, Any]],
) -> RegenerationRunReport:
    decisions: List[RegenerationDecision] = []
    replaced_targets: List[str] = []
    for decision in report.decisions:
        request = decision.request
        if not request:
            decisions.append(decision)
            continue
        page = decision.page
        candidate_best = generated_candidates.get(page)
        if not candidate_best:
            decisions.append(RegenerationDecision(page, decision.target, True, False, False, "No candidates generated.", request, None))
            continue

        previous_path = selected[page - 1] if 0 < page <= len(selected) else ""
        previous = previous_candidates.get(page, {"path": previous_path, "metadata": {}})
        local_prev = _score_local(previous)
        seq_prev = _score_sequence_support(page, previous, sequence_report)
        comp_prev = clamp01(0.7 * local_prev + 0.3 * seq_prev)

        local_new = _score_local(candidate_best)
        seq_new = _score_sequence_support(page, candidate_best, sequence_report)
        comp_new = clamp01(0.7 * local_new + 0.3 * seq_new)

        local_delta = round(local_new - local_prev, 6)
        seq_delta = round(seq_new - seq_prev, 6)
        comp_delta = round(comp_new - comp_prev, 6)
        accept = bool(
            comp_delta >= float(report.config.get("minimum_required_improvement", 0.05))
            and (local_delta >= float(report.config.get("minimum_required_improvement", 0.05)) or seq_delta >= float(report.config.get("minimum_required_improvement", 0.05)))
        )
        comparison = RegenerationComparison(
            page=page,
            previous_path=previous_path,
            candidate_path=str(candidate_best.get("path", "")),
            previous_local_score=local_prev,
            candidate_local_score=local_new,
            local_delta=local_delta,
            previous_sequence_support=seq_prev,
            candidate_sequence_support=seq_new,
            sequence_delta=seq_delta,
            previous_composite_score=round(comp_prev, 6),
            candidate_composite_score=round(comp_new, 6),
            composite_delta=comp_delta,
            accepted=accept,
            reason="Measurable improvement met threshold." if accept else "Improvement below threshold.",
        )

        replaced = False
        reason = comparison.reason
        if accept and previous_path and Path(previous_path).exists() and Path(comparison.candidate_path).exists():
            with Image.open(Path(comparison.candidate_path)) as cand, Image.open(Path(previous_path)) as current:
                out = cand.convert("RGB")
                if out.size != current.size:
                    out = out.resize(current.size, Image.Resampling.LANCZOS)
                out.save(previous_path, "PNG")
            replaced = True
            replaced_targets.append(decision.target)
            reason = "Replacement applied from targeted regeneration candidate."

        decisions.append(
            RegenerationDecision(
                page=page,
                target=decision.target,
                eligible=decision.eligible,
                regenerated=decision.regenerated,
                replaced=replaced,
                reason=reason,
                request=request,
                comparison=comparison,
            )
        )

    return RegenerationRunReport(
        enabled=report.enabled,
        config=report.config,
        provider_available=report.provider_available,
        eligible_targets=report.eligible_targets,
        regenerated_targets=report.regenerated_targets,
        replaced_targets=sorted(replaced_targets),
        replacement_cap_hit=report.replacement_cap_hit or (bool(report.config.get("max_regenerations_per_run", 0)) and len(replaced_targets) >= int(report.config.get("max_regenerations_per_run", 0))),
        decisions=decisions,
        sequence_improvement=report.sequence_improvement,
        notes=report.notes,
    )


def with_sequence_improvement(
    report: RegenerationRunReport,
    *,
    before_score: float | None,
    after_score: float | None,
    re_evaluated: bool,
) -> RegenerationRunReport:
    delta = None
    if before_score is not None and after_score is not None:
        delta = round(float(after_score) - float(before_score), 6)
    return RegenerationRunReport(
        enabled=report.enabled,
        config=report.config,
        provider_available=report.provider_available,
        eligible_targets=report.eligible_targets,
        regenerated_targets=report.regenerated_targets,
        replaced_targets=report.replaced_targets,
        replacement_cap_hit=report.replacement_cap_hit,
        decisions=report.decisions,
        sequence_improvement=RegenerationImprovementSummary(re_evaluated, before_score, after_score, delta),
        notes=report.notes,
    )
