from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from bookforge.saliency_flow import build_saliency_sequence_finding
from bookforge.saliency_flow.types import SaliencySequenceFinding


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


@dataclass(frozen=True)
class ColorTransitionFinding:
    from_page: int
    to_page: int
    expected_mode: str
    expected_strength: float
    realized_delta: float
    severity: float
    score: float
    notes: List[str]
    warnings: List[str]


@dataclass(frozen=True)
class ArchitectureSequenceFinding:
    architecture_variety_score: float
    repeated_pattern_warnings: List[str]
    energy_cluster_warnings: List[str]
    pacing_warnings: List[str]
    text_heavy_cluster_warnings: List[str]
    relief_warnings: List[str]
    summary_score: float


@dataclass(frozen=True)
class EnergyCurveFinding:
    target_curve: List[float]
    realized_curve: List[float]
    flat_segments: List[str]
    spike_segments: List[str]
    climax_warnings: List[str]
    ending_warnings: List[str]
    mismatch_score: float


@dataclass(frozen=True)
class WeakClusterFinding:
    start_page: int
    end_page: int
    reason: str
    severity: str
    pages: List[int]




@dataclass(frozen=True)
class CameraSequenceFinding:
    summary_score: float
    adjacent_repeat_warnings: List[str]
    medium_run_warnings: List[str]
    progression_warnings: List[str]
    opening_warnings: List[str]
    climax_warnings: List[str]
    ending_warnings: List[str]
    repetitive_run_warnings: List[str]

@dataclass(frozen=True)
class BookSequenceReport:
    status: str
    overall_sequence_score: float
    summary_notes: List[str]
    warnings: List[str]
    errors: List[str]
    color_flow_summary_score: float
    architecture_flow_summary_score: float
    energy_curve_summary_score: float
    color_transitions: List[ColorTransitionFinding]
    architecture_flow: ArchitectureSequenceFinding
    energy_curve: EnergyCurveFinding
    weak_clusters: List[WeakClusterFinding]
    camera_sequence: CameraSequenceFinding
    saliency_flow_sequence: SaliencySequenceFinding
    per_page_notes: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_page_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _series_from_qa_attempts(qa_attempts: List[Dict[str, Any]], page_count: int) -> Dict[int, Dict[str, Any]]:
    series: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        page = row.get("page")
        if isinstance(page, int) and 1 <= page <= page_count:
            best = row.get("best", {}) if isinstance(row.get("best", {}), dict) else {}
            if best:
                series[page] = best
    return series


def _build_color_transition_findings(
    transitions: List[Dict[str, Any]],
    qa_by_page: Dict[int, Dict[str, Any]],
    color_pages: Dict[int, Dict[str, Any]],
) -> tuple[List[ColorTransitionFinding], float, List[str]]:
    findings: List[ColorTransitionFinding] = []
    global_warnings: List[str] = []
    transition_scores: List[float] = []
    lightness_run: List[int] = []
    contamination_pages: List[int] = []

    for t in transitions:
        from_page = _safe_page_int(t.get("from_page"))
        to_page = _safe_page_int(t.get("to_page"))
        expected_mode = str(t.get("mode", "blend"))
        expected_strength = float(t.get("strength", 0.5) or 0.5)
        to_best = qa_by_page.get(to_page, {})
        realized_delta = float(to_best.get("page_to_page_hist_drift", 0.0) or 0.0)

        if expected_mode == "hard_cut":
            severity = abs(realized_delta - max(0.45, expected_strength * 0.8))
        else:
            severity = abs(realized_delta - min(0.22, expected_strength * 0.45))
        severity = _clamp01(severity)
        score = _clamp01(1.0 - severity)

        notes: List[str] = []
        warnings: List[str] = []
        if expected_mode == "hard_cut" and realized_delta < 0.28:
            warnings.append("Missing contrast for hard-cut beat/reveal intent.")
        if expected_mode == "blend" and realized_delta > 0.35:
            warnings.append("Abrupt transition where blend was expected.")
        if realized_delta < 0.06:
            notes.append("Transition appears very smooth / low drift.")
        if realized_delta > 0.42:
            notes.append("Transition appears strongly abrupt / high drift.")

        spec_to = color_pages.get(to_page, {})
        forb = spec_to.get("forbidden_colors_lab", []) if isinstance(spec_to, dict) else []
        contamination = float(to_best.get("forbidden_penalty", 0.0) or 0.0)
        if forb and contamination > 0.25:
            warnings.append("Potential forbidden palette contamination.")
            contamination_pages.append(to_page)

        findings.append(
            ColorTransitionFinding(
                from_page=from_page,
                to_page=to_page,
                expected_mode=expected_mode,
                expected_strength=expected_strength,
                realized_delta=realized_delta,
                severity=severity,
                score=score,
                notes=notes,
                warnings=warnings,
            )
        )
        transition_scores.append(score)

    page_numbers = sorted(color_pages.keys())
    for p in page_numbers:
        spec = color_pages.get(p, {})
        target_lightness = float(spec.get("target_lightness", 0.0) or 0.0)
        if not lightness_run or abs(target_lightness - lightness_run[-1]) <= 2:
            lightness_run.append(int(target_lightness))
        else:
            if len(lightness_run) >= 4:
                global_warnings.append("Suspiciously repetitive color run detected (>=4 pages).")
            lightness_run = [int(target_lightness)]
    if len(lightness_run) >= 4:
        global_warnings.append("Suspiciously repetitive color run detected (>=4 pages).")

    if len(contamination_pages) >= 2:
        global_warnings.append(
            f"Unexpected palette contamination cluster near pages {min(contamination_pages)}-{max(contamination_pages)}."
        )

    summary_score = round(mean(transition_scores), 4) if transition_scores else 1.0
    return findings, summary_score, global_warnings


def _build_architecture_flow(
    architecture_plan: List[Dict[str, Any]],
    applied_arch_rows: List[Dict[str, Any]],
) -> ArchitectureSequenceFinding:
    plan_by_page = {_safe_page_int(row.get("page_number")): row for row in architecture_plan if isinstance(row, dict)}
    applied_by_page = {_safe_page_int(row.get("page")): row for row in applied_arch_rows if isinstance(row, dict)}
    pages = sorted(set(plan_by_page.keys()) | set(applied_by_page.keys()))

    arch_types: List[str] = []
    energies: List[float] = []
    repeated_pattern_warnings: List[str] = []
    energy_cluster_warnings: List[str] = []
    pacing_warnings: List[str] = []
    text_heavy_cluster_warnings: List[str] = []
    relief_warnings: List[str] = []

    for p in pages:
        plan = plan_by_page.get(p, {})
        applied = applied_by_page.get(p, {})
        arch_type = str(applied.get("architecture_type") or plan.get("selected_architecture_type") or "unknown")
        arch_types.append(arch_type)
        energies.append(float(plan.get("target_energy", 0.5) or 0.5))

    unique = len(set(arch_types))
    variety_score = round(_clamp01(unique / max(3, len(arch_types) * 0.5)), 4) if arch_types else 1.0

    streak_type = ""
    streak_start = 0
    streak_count = 0
    for idx, arch in enumerate(arch_types, start=1):
        if arch == streak_type:
            streak_count += 1
        else:
            if streak_count >= 3 and streak_type:
                repeated_pattern_warnings.append(f"Pages {streak_start}-{idx-1} repeat architecture '{streak_type}'.")
            streak_type = arch
            streak_start = idx
            streak_count = 1
    if streak_count >= 3 and streak_type:
        repeated_pattern_warnings.append(f"Pages {streak_start}-{len(arch_types)} repeat architecture '{streak_type}'.")

    for i in range(1, len(energies)):
        if abs(energies[i] - energies[i - 1]) < 0.05:
            energy_cluster_warnings.append(f"Pages {i}-{i+1} have very similar planned page energies.")

    for p in pages:
        plan = plan_by_page.get(p, {})
        applied = applied_by_page.get(p, {})
        if str(applied.get("architecture_type", "")).strip() and plan:
            if str(applied.get("architecture_type")) != str(plan.get("selected_architecture_type")):
                pacing_warnings.append(
                    f"Page {p} realized architecture '{applied.get('architecture_type')}' differs from planned pacing type '{plan.get('selected_architecture_type')}'."
                )

    text_heavy_pages = [p for p in pages if str(applied_by_page.get(p, {}).get("architecture_type", "")) == "text_dominant"]
    if len(text_heavy_pages) >= 3:
        text_heavy_cluster_warnings.append(
            f"Text-heavy clustering detected around pages {min(text_heavy_pages)}-{max(text_heavy_pages)}."
        )

    if pages:
        last_quarter_start = max(1, int(len(pages) * 0.75))
        near_resolution = [p for p in pages if p >= last_quarter_start]
        if near_resolution and not any(
            str(applied_by_page.get(p, {}).get("architecture_type", "")) in {"vignette", "spot_illustration"}
            for p in near_resolution
        ):
            relief_warnings.append("Missing breathing/relief structures near resolution pages.")

    penalties = (
        0.12 * len(repeated_pattern_warnings)
        + 0.05 * len(energy_cluster_warnings)
        + 0.08 * len(pacing_warnings)
        + 0.08 * len(text_heavy_cluster_warnings)
        + 0.08 * len(relief_warnings)
    )
    summary_score = round(_clamp01(variety_score - penalties), 4)

    return ArchitectureSequenceFinding(
        architecture_variety_score=variety_score,
        repeated_pattern_warnings=repeated_pattern_warnings,
        energy_cluster_warnings=energy_cluster_warnings,
        pacing_warnings=pacing_warnings,
        text_heavy_cluster_warnings=text_heavy_cluster_warnings,
        relief_warnings=relief_warnings,
        summary_score=summary_score,
    )


def _build_energy_curve(
    architecture_plan: List[Dict[str, Any]],
    applied_arch_rows: List[Dict[str, Any]],
    premium_qc_pages: List[Dict[str, Any]],
) -> EnergyCurveFinding:
    plan_by_page = {_safe_page_int(row.get("page_number")): row for row in architecture_plan if isinstance(row, dict)}
    applied_by_page = {_safe_page_int(row.get("page")): row for row in applied_arch_rows if isinstance(row, dict)}
    qc_by_page = {_safe_page_int(row.get("page")): row for row in premium_qc_pages if isinstance(row, dict)}
    pages = sorted(set(plan_by_page.keys()) | set(applied_by_page.keys()) | set(qc_by_page.keys()))

    target_curve: List[float] = []
    realized_curve: List[float] = []
    flat_segments: List[str] = []
    spike_segments: List[str] = []
    climax_warnings: List[str] = []
    ending_warnings: List[str] = []

    energy_map = {
        "wordless_spread": 0.95,
        "full_bleed_spread": 0.88,
        "panel_sequence": 0.75,
        "inset_composite": 0.65,
        "full_bleed_single": 0.62,
        "vignette": 0.45,
        "spot_illustration": 0.35,
        "text_dominant": 0.28,
    }
    for p in pages:
        target = float(plan_by_page.get(p, {}).get("target_energy", 0.5) or 0.5)
        arch_type = str(applied_by_page.get(p, {}).get("architecture_type") or plan_by_page.get(p, {}).get("selected_architecture_type") or "")
        arch_proxy = energy_map.get(arch_type, 0.5)
        visual_proxy = float((qc_by_page.get(p, {}).get("visual_critic_scores", {}) or {}).get("composition_score", 0.5) or 0.5)
        realized = _clamp01(0.6 * arch_proxy + 0.4 * visual_proxy)
        target_curve.append(target)
        realized_curve.append(realized)

    for i in range(1, len(realized_curve)):
        delta = realized_curve[i] - realized_curve[i - 1]
        if abs(delta) < 0.04:
            flat_segments.append(f"Pages {i}-{i+1} appear flatter than intended.")
        if abs(delta) > 0.42:
            spike_segments.append(f"Pages {i}-{i+1} show a jarring energy spike.")

    if target_curve and realized_curve:
        peak_target = max(range(len(target_curve)), key=lambda idx: target_curve[idx])
        if realized_curve[peak_target] < min(0.75, target_curve[peak_target] - 0.12):
            climax_warnings.append(f"Planned climax around page {peak_target + 1} does not stand out enough.")
        end_idx = len(realized_curve) - 1
        if realized_curve[end_idx] > min(0.55, target_curve[end_idx] + 0.1):
            ending_warnings.append("Ending remains visually energetic instead of resolving.")

    diffs = [abs(t - r) for t, r in zip(target_curve, realized_curve)]
    mismatch = round(_clamp01(1.0 - (mean(diffs) if diffs else 0.0)), 4)

    return EnergyCurveFinding(
        target_curve=[round(v, 4) for v in target_curve],
        realized_curve=[round(v, 4) for v in realized_curve],
        flat_segments=flat_segments,
        spike_segments=spike_segments,
        climax_warnings=climax_warnings,
        ending_warnings=ending_warnings,
        mismatch_score=mismatch,
    )


def _build_weak_clusters(
    page_count: int,
    applied_arch_rows: List[Dict[str, Any]],
    premium_qc_pages: List[Dict[str, Any]],
    color_transition_findings: List[ColorTransitionFinding],
) -> List[WeakClusterFinding]:
    clusters: List[WeakClusterFinding] = []
    applied_by_page = {_safe_page_int(row.get("page")): row for row in applied_arch_rows if isinstance(row, dict)}
    qc_by_page = {_safe_page_int(row.get("page")): row for row in premium_qc_pages if isinstance(row, dict)}
    transition_by_to_page = {row.to_page: row for row in color_transition_findings}

    for start in range(1, max(page_count - 1, 1)):
        end = min(page_count, start + 3)
        pages = list(range(start, end + 1))
        if len(pages) < 2:
            continue
        arch_types = [str(applied_by_page.get(p, {}).get("architecture_type", "unknown")) for p in pages]
        qc_scores = [float(qc_by_page.get(p, {}).get("score", 1.0) or 1.0) for p in pages]
        weak_visual = [p for p in pages if float(qc_by_page.get(p, {}).get("score", 1.0) or 1.0) < 0.78]
        flat_transitions = [p for p in pages if transition_by_to_page.get(p) and transition_by_to_page[p].realized_delta < 0.08]
        gutter_issues = [
            p
            for p in pages
            if any("gutter" in str(w).lower() for w in (qc_by_page.get(p, {}).get("continuity_warnings", []) or []))
        ]

        if len(set(arch_types)) <= 1 and len(pages) >= 3:
            clusters.append(
                WeakClusterFinding(
                    start_page=start,
                    end_page=end,
                    reason=f"Pages {start}-{end} feel visually repetitive (architecture repetition).",
                    severity="warning",
                    pages=pages,
                )
            )
        if len(weak_visual) >= 2:
            clusters.append(
                WeakClusterFinding(
                    start_page=start,
                    end_page=end,
                    reason=f"Pages {start}-{end} include multiple adjacent weak visual scores.",
                    severity="warning",
                    pages=weak_visual,
                )
            )
        if len(flat_transitions) >= 2:
            clusters.append(
                WeakClusterFinding(
                    start_page=start,
                    end_page=end,
                    reason=f"Pages {start}-{end} lack sufficient transition contrast.",
                    severity="warning",
                    pages=flat_transitions,
                )
            )
        if gutter_issues:
            clusters.append(
                WeakClusterFinding(
                    start_page=start,
                    end_page=end,
                    reason=f"Pages {start}-{end} show clustered text-zone/gutter continuity concerns.",
                    severity="info",
                    pages=gutter_issues,
                )
            )
        if mean(qc_scores) >= 0.9 and len(set(arch_types)) >= 2:
            clusters.append(
                WeakClusterFinding(
                    start_page=start,
                    end_page=end,
                    reason=f"Pages {start}-{end} resolve well.",
                    severity="positive",
                    pages=pages,
                )
            )

    deduped: Dict[tuple[int, int, str], WeakClusterFinding] = {}
    for c in clusters:
        deduped[(c.start_page, c.end_page, c.reason)] = c
    return list(deduped.values())


def _build_camera_sequence_findings(
    page_count: int,
    camera_sequence_plan: Dict[int, Dict[str, Any]],
    architecture_plan: List[Dict[str, Any]],
) -> CameraSequenceFinding:
    rows = [camera_sequence_plan[p] for p in sorted(camera_sequence_plan.keys()) if p > 0]
    shots = [str(r.get("shot_type", "")) for r in rows]
    adjacent_repeat_warnings: List[str] = []
    medium_run_warnings: List[str] = []
    progression_warnings: List[str] = []
    opening_warnings: List[str] = []
    climax_warnings: List[str] = []
    ending_warnings: List[str] = []
    repetitive_run_warnings: List[str] = []

    for i in range(1, len(rows)):
        if shots[i] and shots[i] == shots[i - 1]:
            adjacent_repeat_warnings.append(f"Pages {rows[i-1].get('page_number')}-{rows[i].get('page_number')} repeat shot type '{shots[i]}'.")

    run = 0
    for shot in shots:
        if shot == "medium_interaction":
            run += 1
        else:
            if run >= 3:
                medium_run_warnings.append("Run of >=3 medium_interaction shots reduces visual variety.")
            run = 0
    if run >= 3:
        medium_run_warnings.append("Run of >=3 medium_interaction shots reduces visual variety.")

    for i in range(1, len(rows)):
        d0 = str(rows[i - 1].get("target_distance_class", ""))
        d1 = str(rows[i].get("target_distance_class", ""))
        if d0 == d1 and d0 in {"wide", "close"}:
            progression_warnings.append(f"Pages {rows[i-1].get('page_number')}-{rows[i].get('page_number')} have weak framing contrast.")

    if rows and str(rows[0].get("shot_type", "")) != "establishing_wide":
        opening_warnings.append("Opening page is not using establishing_wide framing.")

    climax_pages = {int(r.get("page_number", 0)): str(r.get("shot_type", "")) for r in rows if str(r.get("narrative_reason", "")).startswith("climax") or str(r.get("narrative_reason", "")).startswith("reveal")}
    all_recent = shots[:-1]
    for p, shot in climax_pages.items():
        if shot and shot in all_recent[-3:]:
            climax_warnings.append(f"Page {p} climax/reveal uses recently repeated shot '{shot}'.")

    if rows and str(rows[-1].get("shot_type", "")) in {"dutch_tilt", "worms_eye"}:
        ending_warnings.append("Ending shot remains unstable/chaotic; prefer calmer return framing.")

    for i in range(len(shots) - 3):
        span = shots[i:i+4]
        if len(set(span)) <= 2:
            repetitive_run_warnings.append(f"Pages {i+1}-{i+4} show repetitive camera language.")

    penalties = 0.12*len(adjacent_repeat_warnings)+0.08*len(medium_run_warnings)+0.07*len(progression_warnings)+0.12*len(opening_warnings)+0.1*len(climax_warnings)+0.1*len(ending_warnings)+0.08*len(repetitive_run_warnings)
    summary_score = round(_clamp01(1.0 - penalties), 4)

    return CameraSequenceFinding(
        summary_score=summary_score,
        adjacent_repeat_warnings=adjacent_repeat_warnings,
        medium_run_warnings=medium_run_warnings,
        progression_warnings=progression_warnings,
        opening_warnings=opening_warnings,
        climax_warnings=climax_warnings,
        ending_warnings=ending_warnings,
        repetitive_run_warnings=repetitive_run_warnings,
    )


def build_book_sequence_report(
    *,
    page_count: int,
    color_script: Dict[str, Any] | None,
    architecture_plan: List[Dict[str, Any]] | None,
    applied_arch_rows: List[Dict[str, Any]] | None,
    qa_attempts: List[Dict[str, Any]] | None,
    premium_qc: Dict[str, Any] | None,
    camera_sequence_plan: Dict[int, Dict[str, Any]] | None = None,
) -> BookSequenceReport:
    color_script = color_script if isinstance(color_script, dict) else {}
    architecture_plan = architecture_plan if isinstance(architecture_plan, list) else []
    applied_arch_rows = applied_arch_rows if isinstance(applied_arch_rows, list) else []
    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []
    premium_qc = premium_qc if isinstance(premium_qc, dict) else {}
    camera_sequence_plan = camera_sequence_plan if isinstance(camera_sequence_plan, dict) else {}

    qa_by_page = _series_from_qa_attempts(qa_attempts, page_count)
    color_pages = {
        _safe_page_int(row.get("page_number")): row
        for row in color_script.get("pages", [])
        if isinstance(row, dict) and _safe_page_int(row.get("page_number")) > 0
    }
    transitions = [t for t in color_script.get("transitions", []) if isinstance(t, dict)]
    color_findings, color_score, color_warnings = _build_color_transition_findings(transitions, qa_by_page, color_pages)

    architecture_flow = _build_architecture_flow(architecture_plan, applied_arch_rows)
    premium_pages = premium_qc.get("pages", []) if isinstance(premium_qc.get("pages", []), list) else []
    energy_curve = _build_energy_curve(architecture_plan, applied_arch_rows, premium_pages)
    weak_clusters = _build_weak_clusters(page_count, applied_arch_rows, premium_pages, color_findings)
    camera_sequence = _build_camera_sequence_findings(page_count, camera_sequence_plan, architecture_plan)
    saliency_flow_sequence = build_saliency_sequence_finding(page_count, qa_attempts, camera_sequence_plan)

    warnings: List[str] = []
    errors: List[str] = []
    summary_notes: List[str] = []
    if not color_script:
        warnings.append("Color planning artifacts absent; color-flow diagnostics are limited.")
    if not architecture_plan:
        warnings.append("Architecture planning artifacts absent; architecture-flow diagnostics are limited.")
    if not applied_arch_rows:
        warnings.append("Applied architecture metadata absent; realized-flow proxies are limited.")
    if not premium_pages:
        warnings.append("Premium visual QC pages absent; energy and weak-cluster diagnostics are limited.")
    if not camera_sequence_plan:
        warnings.append("Camera sequence plan absent; cinematic diagnostics are limited.")
    if not qa_attempts:
        warnings.append("QA attempts absent; saliency-flow sequence diagnostics are limited.")

    summary_notes.extend(color_warnings)
    summary_notes.extend(architecture_flow.repeated_pattern_warnings[:2])
    summary_notes.extend(energy_curve.climax_warnings[:1])
    summary_notes.extend(camera_sequence.opening_warnings[:1])
    summary_notes.extend(saliency_flow_sequence.camera_mismatch_warnings[:1])
    if not summary_notes:
        summary_notes.append("Sequence diagnostics completed with no major warnings.")

    overall = round(
        _clamp01(0.27 * color_score + 0.25 * architecture_flow.summary_score + 0.2 * energy_curve.mismatch_score + 0.13 * camera_sequence.summary_score + 0.15 * saliency_flow_sequence.summary_score),
        4,
    )

    per_page_notes = []
    for p in range(1, page_count + 1):
        per_page_notes.append(
            {
                "page": p,
                "architecture_type": str(
                    next((r.get("architecture_type") for r in applied_arch_rows if _safe_page_int(r.get("page")) == p), "")
                ),
                "premium_qc_score": float(
                    next((r.get("score") for r in premium_pages if _safe_page_int(r.get("page")) == p), 0.0) or 0.0
                ),
                "color_transition_to_page_score": next((f.score for f in color_findings if f.to_page == p), None),
                "shot_type": str((camera_sequence_plan.get(p) or {}).get("shot_type", "")),
                "saliency_flow_score": float(((qa_by_page.get(p, {}).get("metadata", {}) or {}).get("saliency_flow_score", {}) or {}).get("composite_score", 0.0) or 0.0),
            }
        )

    return BookSequenceReport(
        status="PASS" if not errors else "WARN",
        overall_sequence_score=overall,
        summary_notes=summary_notes,
        warnings=warnings,
        errors=errors,
        color_flow_summary_score=color_score,
        architecture_flow_summary_score=architecture_flow.summary_score,
        energy_curve_summary_score=energy_curve.mismatch_score,
        color_transitions=color_findings,
        architecture_flow=architecture_flow,
        energy_curve=energy_curve,
        weak_clusters=weak_clusters,
        camera_sequence=camera_sequence,
        saliency_flow_sequence=saliency_flow_sequence,
        per_page_notes=per_page_notes,
    )


def write_book_sequence_report(path: Path, report: BookSequenceReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

