from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from bookforge.sequence_optimizer.scoring import (
    composite_delta,
    local_score_bundle,
    move_component_deltas,
    objective_delta,
    sequence_summary_from_report,
)
from bookforge.sequence_optimizer.types import (
    SequenceOptimizationCandidate,
    SequenceOptimizationConfig,
    SequenceOptimizationDecision,
    SequenceOptimizationImprovement,
    SequenceOptimizationMove,
    SequenceOptimizationReport,
)


def _flag(name: str, default: str) -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def build_sequence_optimization_config() -> SequenceOptimizationConfig:
    return SequenceOptimizationConfig(
        enabled=_flag("BOOKFORGE_SEQUENCE_OPTIMIZATION", "false"),
        max_pages_considered=max(0, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_PAGES", "10") or 10)),
        max_moves_per_run=max(0, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_MOVES", "2") or 2)),
        max_candidates_per_page=max(1, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_CANDIDATES_PER_PAGE", "3") or 3)),
        minimum_net_improvement=max(0.0, float(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT", "0.03") or 0.03)),
        max_local_regression_tolerance=max(0.0, float(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_LOCAL_REGRESSION", "0.015") or 0.015)),
        opening_pages_protection=max(0, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION", "1") or 1)),
        climax_pages_protection=max(0, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION", "1") or 1)),
        ending_pages_protection=max(0, int(os.getenv("BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION", "1") or 1)),
    )


def _latest_pool_by_page(qa_attempts: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    pool: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        page = row.get("page")
        if not isinstance(page, int):
            continue
        variants = row.get("variants", [])
        best = row.get("best", {})
        if not isinstance(variants, list) or not isinstance(best, dict) or len(variants) < 2:
            continue
        prev = pool.get(page)
        if prev is None or int(row.get("attempt", 0) or 0) >= int(prev.get("attempt", 0) or 0):
            pool[page] = row
    return pool


def _protected(page: int, page_count: int, cfg: SequenceOptimizationConfig) -> bool:
    if page <= cfg.opening_pages_protection:
        return True
    if page > max(0, page_count - cfg.ending_pages_protection):
        return True
    climax_start = max(1, page_count - cfg.ending_pages_protection - cfg.climax_pages_protection + 1)
    climax_end = max(1, page_count - cfg.ending_pages_protection)
    return climax_start <= page <= climax_end and cfg.climax_pages_protection > 0


def _priority_pages(sequence_report: Dict[str, Any], page_count: int) -> List[int]:
    weak: List[int] = []
    for cluster in sequence_report.get("weak_clusters", []):
        if not isinstance(cluster, dict):
            continue
        for page in cluster.get("pages", []):
            if isinstance(page, int) and 1 <= page <= page_count and page not in weak:
                weak.append(page)
    for row in sequence_report.get("per_page_notes", []):
        if not isinstance(row, dict):
            continue
        page = int(row.get("page", 0) or 0)
        if page <= 0 or page in weak:
            continue
        premium = float(row.get("premium_qc_score", 1.0) or 1.0)
        trans = row.get("color_transition_to_page_score")
        if premium < 0.8 or (trans is not None and float(trans) < 0.75):
            weak.append(page)
    if not weak:
        weak = list(range(1, page_count + 1))
    return weak


def _neighbor_local_bundles(page: int, pools: Dict[int, Dict[str, Any]]) -> List[Dict[str, float]]:
    bundles: List[Dict[str, float]] = []
    for neighbor_page in (page - 1, page + 1):
        attempt = pools.get(neighbor_page)
        if not isinstance(attempt, dict):
            continue
        best = attempt.get("best", {}) if isinstance(attempt.get("best", {}), dict) else {}
        if best:
            bundles.append(local_score_bundle(best))
    return bundles


def _evaluate_move(
    *,
    cfg: SequenceOptimizationConfig,
    page: int,
    idx: int,
    current: Dict[str, Any],
    alternative: Dict[str, Any],
    sequence_report: Dict[str, Any],
    before_summary: Dict[str, float],
    neighbor_local_bundles: List[Dict[str, float]],
    page_count: int,
) -> SequenceOptimizationMove:
    deltas = move_component_deltas(
        page=page,
        current=current,
        alternative=alternative,
        sequence_report=sequence_report,
        opening_window=max(1, cfg.opening_pages_protection),
        climax_window=max(1, cfg.climax_pages_protection),
        ending_window=max(1, cfg.ending_pages_protection),
        page_count=page_count,
        neighbor_local_bundles=neighbor_local_bundles,
    )
    before_local = local_score_bundle(current)
    after_local = local_score_bundle(alternative)
    local_delta = float(deltas.get("local_composite", 0.0) or 0.0)
    raw_net = composite_delta(deltas)
    objective_net = objective_delta(
        deltas=deltas,
        before_summary=before_summary,
        weak_cluster_page=any(page in (c.get("pages") or []) for c in sequence_report.get("weak_clusters", []) if isinstance(c, dict)),
    )

    checks = {
        "objective_minimum": objective_net >= cfg.minimum_net_improvement,
        "local_floor": local_delta >= -cfg.max_local_regression_tolerance,
        "saliency_floor": float(deltas.get("saliency_flow_score", 0.0) or 0.0) >= -0.02,
        "camera_floor": float(deltas.get("camera_flow_score", 0.0) or 0.0) >= -0.02,
        "typography_floor": float(deltas.get("typography_sequence_score", 0.0) or 0.0) >= -0.015,
        "hidden_world_floor": float(deltas.get("hidden_world_continuity_score", 0.0) or 0.0) >= -0.015,
        "architecture_floor": float(deltas.get("architecture_flow_score", 0.0) or 0.0) >= -0.015,
        "summary_without_raw_collapse": objective_net > 0.0 or raw_net >= 0.0,
    }
    accepted = all(checks.values())

    failed = [k for k, ok in checks.items() if not ok]
    reason = "Accepted: objective gain with local floors respected."
    if not accepted:
        reason = f"Rejected: failed checks {', '.join(failed)}."

    notes = [
        f"raw_net={raw_net:.4f}",
        f"objective_net={objective_net:.4f}",
        f"local_delta={local_delta:.4f}",
    ]
    notes.extend(f"check:{name}={'pass' if ok else 'fail'}" for name, ok in checks.items())

    cand = SequenceOptimizationCandidate(
        page=page,
        scope="page",
        selected_candidate_path=str(current.get("path", "")),
        runner_up_candidate_path=str(alternative.get("path", "")),
        selected_candidate_id=f"p{page}:selected",
        runner_up_candidate_id=f"p{page}:runner_up:{idx}",
        local_score_bundle=before_local,
        sequence_contribution_bundle={k: float(v) for k, v in deltas.items() if k != "local_composite"},
        warnings=[],
        notes=[f"neighbor_context_count={len(neighbor_local_bundles)}"],
    )
    return SequenceOptimizationMove(
        page,
        cand,
        before_local,
        after_local,
        deltas,
        objective_net,
        local_delta,
        accepted,
        reason,
        warnings=[],
        notes=notes,
    )


def run_sequence_optimization(
    *,
    selected: List[str],
    qa_attempts: List[Dict[str, Any]],
    sequence_report: Dict[str, Any] | None,
) -> SequenceOptimizationReport:
    cfg = build_sequence_optimization_config()
    before_summary = sequence_summary_from_report(sequence_report)
    if not cfg.enabled:
        improvement = SequenceOptimizationImprovement(before_summary["overall"], before_summary["overall"], 0.0, {})
        return SequenceOptimizationReport(False, cfg.to_dict(), [], 0, [], [], [], False, before_summary, before_summary, improvement, warnings=[], limitations=["Feature flag disabled."])
    if not isinstance(sequence_report, dict):
        improvement = SequenceOptimizationImprovement(before_summary["overall"], before_summary["overall"], 0.0, {})
        return SequenceOptimizationReport(True, cfg.to_dict(), [], 0, [], [], [], False, before_summary, before_summary, improvement, warnings=["Missing sequence report; optimizer is a no-op."], limitations=[])

    pools = _latest_pool_by_page(qa_attempts)
    page_count = len(selected)
    ordered_pages = [p for p in _priority_pages(sequence_report, page_count) if p in pools]
    pages_considered = ordered_pages[: cfg.max_pages_considered]
    warnings: List[str] = []
    limitations: List[str] = []
    if not pages_considered:
        warnings.append("No pages with runner-up candidate pools were available.")

    all_moves: List[SequenceOptimizationMove] = []
    decisions: List[SequenceOptimizationDecision] = []

    for page in pages_considered:
        attempt = pools[page]
        current = attempt.get("best", {}) if isinstance(attempt.get("best", {}), dict) else {}
        current_path = str(current.get("path", ""))
        protected = _protected(page, page_count, cfg)
        if protected:
            decisions.append(SequenceOptimizationDecision(page, True, False, selected[page - 1], selected[page - 1], "Protected opening/climax/ending page.", None, [], [], ["By design this page is immutable for bounded pass."]))
            continue

        variants = [v for v in attempt.get("variants", []) if isinstance(v, dict)]
        runner_ups = [v for v in variants if str(v.get("path", "")) and str(v.get("path", "")) != current_path]
        if not runner_ups:
            decisions.append(SequenceOptimizationDecision(page, True, False, selected[page - 1], selected[page - 1], "No runner-up pool for page.", None, [], ["Runner-up variants unavailable."], []))
            continue

        # exploit runner-up pools by ranking via local composite then evaluating bounded prefix.
        ranked_runner_ups = sorted(runner_ups, key=lambda row: (-local_score_bundle(row)["local_composite"], str(row.get("path", ""))))
        bounded_runner_ups = ranked_runner_ups[: cfg.max_candidates_per_page]
        rejected: List[SequenceOptimizationMove] = []
        best_move: SequenceOptimizationMove | None = None
        neighbor_bundles = _neighbor_local_bundles(page, pools)

        for idx, alt in enumerate(bounded_runner_ups, start=1):
            move = _evaluate_move(
                cfg=cfg,
                page=page,
                idx=idx,
                current=current,
                alternative=alt,
                sequence_report=sequence_report,
                before_summary=before_summary,
                neighbor_local_bundles=neighbor_bundles,
                page_count=page_count,
            )
            all_moves.append(move)
            if best_move is None or move.net_delta > best_move.net_delta or (
                move.net_delta == best_move.net_delta and move.local_delta > best_move.local_delta
            ):
                best_move = move
            if not move.accepted:
                rejected.append(move)

        decisions.append(
            SequenceOptimizationDecision(
                page=page,
                considered=True,
                accepted=bool(best_move and best_move.accepted),
                selected_before=selected[page - 1],
                selected_after=(best_move.candidate.runner_up_candidate_path if best_move and best_move.accepted else selected[page - 1]),
                reason=(
                    "Accepted highest-objective candidate from bounded runner-up pool."
                    if best_move and best_move.accepted
                    else "No candidate met bounded objective and floor checks."
                ),
                best_move=best_move,
                rejected_moves=rejected,
                warnings=[],
                notes=[f"runner_up_pool_size={len(runner_ups)}", f"runner_up_evaluated={len(bounded_runner_ups)}"],
            )
        )

    accepted_sorted = sorted([m for m in all_moves if m.accepted], key=lambda m: (-m.net_delta, -m.local_delta, m.page, m.candidate.runner_up_candidate_path))
    accepted: List[SequenceOptimizationMove] = []
    used_pages: set[int] = set()
    for move in accepted_sorted:
        if len(accepted) >= cfg.max_moves_per_run:
            break
        if move.page in used_pages:
            continue
        accepted.append(move)
        used_pages.add(move.page)

    component_deltas: Dict[str, float] = {}
    for move in accepted:
        for key, value in move.deltas.items():
            if key == "local_composite":
                continue
            component_deltas[key] = round(component_deltas.get(key, 0.0) + float(value), 6)
    overall_delta = round(sum(component_deltas.values()) / 10.0, 6) if component_deltas else 0.0
    after_summary = dict(before_summary)
    for k, v in component_deltas.items():
        after_summary[k] = round(after_summary.get(k, 0.0) + v, 6)
    after_summary["overall"] = round(before_summary.get("overall", 0.0) + overall_delta, 6)

    improvement = SequenceOptimizationImprovement(
        before_overall_sequence_score=before_summary.get("overall", 0.0),
        after_overall_sequence_score=after_summary.get("overall", 0.0),
        net_delta=overall_delta,
        component_deltas=component_deltas,
    )
    cap_hit = len(accepted) >= cfg.max_moves_per_run and len([m for m in all_moves if m.accepted]) > len(accepted)
    if cap_hit:
        limitations.append("Accepted move cap reached before applying all qualifying moves.")
    return SequenceOptimizationReport(
        enabled=True,
        config=cfg.to_dict(),
        pages_considered=pages_considered,
        candidate_moves_considered=len(all_moves),
        accepted_moves=accepted,
        rejected_moves=[m for m in all_moves if not m.accepted],
        decisions=decisions,
        cap_hit=cap_hit,
        before_summary=before_summary,
        after_summary=after_summary,
        net_improvement=improvement,
        warnings=warnings,
        limitations=limitations,
    )


def accepted_move_paths(report: SequenceOptimizationReport) -> List[Tuple[int, str]]:
    return [(m.page, m.candidate.runner_up_candidate_path) for m in report.accepted_moves if m.accepted]
