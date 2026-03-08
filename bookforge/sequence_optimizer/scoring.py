from __future__ import annotations

from typing import Any, Dict, List

from bookforge.scoring_registry import scoring_registry, transition_target
from bookforge.utils import clamp01


def local_score_bundle(candidate: Dict[str, Any]) -> Dict[str, float]:
    meta = candidate.get("metadata", {}) if isinstance(candidate.get("metadata", {}), dict) else {}
    color = float(((meta.get("color_score") or {}).get("composite_score", 0.5)) or 0.5)
    ensemble = float(((meta.get("visual_ensemble") or {}).get("ensemble_score", 0.5)) or 0.5)
    architecture = float(((meta.get("page_architecture_score") or {}).get("composite_score", 0.5)) or 0.5)
    saliency = float(((meta.get("saliency_flow_score") or {}).get("composite_score", 0.5)) or 0.5)
    shot = float(((meta.get("shot_adherence_score") or {}).get("composite_score", 0.5)) or 0.5)
    hidden_world = float(((meta.get("hidden_world_score") or {}).get("composite_score", 0.5)) or 0.5)
    character = float(((meta.get("character_commercial_score") or {}).get("composite_score", 0.5)) or 0.5)
    typography_proxy = clamp01(1.0 - float(candidate.get("focus_bleed_overlap", 0.15) or 0.15))
    dual_audience = float(((meta.get("dual_audience_score") or {}).get("composite_score", 0.5)) or 0.5)
    page_turn = float(((meta.get("page_turn_tension_score") or {}).get("page_turn_tension_score", 0.5)) or 0.5)
    weights = scoring_registry().local_candidate.sequence_optimizer_local_weights
    composite = clamp01(weights["color"] * color + weights["ensemble"] * ensemble + weights["architecture"] * architecture + weights["saliency"] * saliency + weights["camera"] * shot + weights["hidden_world"] * hidden_world + weights["character"] * character + weights["typography"] * typography_proxy + weights["dual_audience"] * dual_audience + weights["page_turn_tension"] * page_turn)
    return {
        "color": color,
        "architecture": architecture,
        "camera": shot,
        "saliency": saliency,
        "typography": typography_proxy,
        "hidden_world": hidden_world,
        "character": character,
        "ensemble": ensemble,
        "dual_audience": dual_audience,
        "page_turn_tension": page_turn,
        "local_composite": round(composite, 6),
    }


def sequence_summary_from_report(sequence_report: Dict[str, Any] | None) -> Dict[str, float]:
    if not isinstance(sequence_report, dict):
        return {
            "overall": 0.0,
            "color_flow_score": 0.0,
            "architecture_flow_score": 0.0,
            "camera_flow_score": 0.0,
            "saliency_flow_score": 0.0,
            "typography_sequence_score": 0.0,
            "hidden_world_continuity_score": 0.0,
            "storefront_opening_score": 0.0,
            "character_consistency_score": 0.0,
            "layout_search_support_score": 0.0,
            "weak_cluster_reduction_score": 0.0,
            "dual_audience_balance_score": 0.0,
            "page_turn_tension_summary_score": 0.0,
        }
    saliency = float(((sequence_report.get("saliency_flow_sequence") or {}).get("summary_score", 0.0)) or 0.0)
    typography = float(((sequence_report.get("typography_sequence") or {}).get("summary_score", 0.0)) or 0.0)
    hidden = float(((sequence_report.get("hidden_world_sequence") or {}).get("summary_score", 0.0)) or 0.0)
    camera = float(((sequence_report.get("camera_sequence") or {}).get("summary_score", 0.0)) or 0.0)
    character = float(((sequence_report.get("character_commercial_summary") or {}).get("summary_score", 0.0)) or 0.0)
    layout = float(((sequence_report.get("layout_search_summary") or {}).get("summary_score", 0.0)) or 0.0)
    weak = float(max(0.0, 1.0 - 0.15 * len(sequence_report.get("weak_clusters", []))))
    dual_summary = (sequence_report.get("dual_audience_summary") or {}) if isinstance(sequence_report.get("dual_audience_summary"), dict) else {}
    page_turn_summary = (sequence_report.get("page_turn_tension_summary") or {}) if isinstance(sequence_report.get("page_turn_tension_summary"), dict) else {}
    return {
        "overall": float(sequence_report.get("overall_sequence_score", 0.0) or 0.0),
        "color_flow_score": float(sequence_report.get("color_flow_summary_score", 0.0) or 0.0),
        "architecture_flow_score": float(sequence_report.get("architecture_flow_summary_score", 0.0) or 0.0),
        "camera_flow_score": camera,
        "saliency_flow_score": saliency,
        "typography_sequence_score": typography,
        "hidden_world_continuity_score": hidden,
        "storefront_opening_score": 0.0,
        "character_consistency_score": character,
        "layout_search_support_score": layout,
        "weak_cluster_reduction_score": weak,
        "dual_audience_balance_score": float(dual_summary.get("summary_score", 0.0) or 0.0),
        "page_turn_tension_summary_score": float(page_turn_summary.get("summary_score", 0.0) or 0.0),
    }


def page_is_weak_cluster(page: int, sequence_report: Dict[str, Any]) -> bool:
    for row in sequence_report.get("weak_clusters", []):
        if not isinstance(row, dict):
            continue
        pages = row.get("pages", [])
        severity = str(row.get("severity", "")).lower()
        if severity in {"warning", "error"} and isinstance(pages, list) and page in pages:
            return True
    return False


def transition_fit(page: int, candidate: Dict[str, Any], sequence_report: Dict[str, Any]) -> float:
    transitions = sequence_report.get("color_transitions", []) if isinstance(sequence_report, dict) else []
    row = next((t for t in transitions if int(t.get("to_page", 0) or 0) == page), None)
    if not row:
        return 0.5
    mode = str(row.get("expected_mode", "blend"))
    strength = float(row.get("expected_strength", 0.5) or 0.5)
    target = transition_target(mode, strength)
    drift = float(candidate.get("page_to_page_hist_drift", 0.0) or 0.0)
    return clamp01(1.0 - abs(drift - target))


def move_component_deltas(
    *,
    page: int,
    current: Dict[str, Any],
    alternative: Dict[str, Any],
    sequence_report: Dict[str, Any],
    opening_window: int,
    climax_window: int,
    ending_window: int,
    page_count: int,
    neighbor_local_bundles: List[Dict[str, float]] | None = None,
) -> Dict[str, float]:
    before = local_score_bundle(current)
    after = local_score_bundle(alternative)
    opening = page <= opening_window
    climax_start = max(1, page_count - ending_window - climax_window + 1)
    climax = climax_start <= page < max(1, page_count - ending_window + 1)
    ending = page > max(0, page_count - ending_window)

    neighbors = [n for n in (neighbor_local_bundles or []) if isinstance(n, dict)]

    def _continuity_delta(key: str) -> float:
        if not neighbors:
            return 0.0
        before_fit = sum(1.0 - abs(float(before.get(key, 0.5)) - float(n.get(key, 0.5))) for n in neighbors) / len(neighbors)
        after_fit = sum(1.0 - abs(float(after.get(key, 0.5)) - float(n.get(key, 0.5))) for n in neighbors) / len(neighbors)
        return clamp01(after_fit) - clamp01(before_fit)

    transition_delta = transition_fit(page, alternative, sequence_report) - transition_fit(page, current, sequence_report)
    color_delta = 0.55 * _continuity_delta("color") + 0.45 * transition_delta
    architecture_delta = (after["architecture"] - before["architecture"]) + 0.35 * _continuity_delta("architecture")
    camera_delta = (after["camera"] - before["camera"]) + 0.35 * _continuity_delta("camera")
    saliency_delta = (after["saliency"] - before["saliency"]) + 0.35 * _continuity_delta("saliency")
    typography_delta = (after["typography"] - before["typography"]) + 0.25 * _continuity_delta("typography")
    hidden_delta = (after["hidden_world"] - before["hidden_world"]) + 0.25 * _continuity_delta("hidden_world")
    character_delta = after["character"] - before["character"]
    layout_delta = 0.5 * ((after["architecture"] + after["saliency"]) - (before["architecture"] + before["saliency"]))
    dual_delta = after["dual_audience"] - before["dual_audience"]
    page_turn_delta = after["page_turn_tension"] - before["page_turn_tension"]
    weak_delta = max(0.0, after["local_composite"] - before["local_composite"]) if page_is_weak_cluster(page, sequence_report) else 0.0
    storefront_delta = (after["ensemble"] - before["ensemble"]) if opening else 0.0
    if climax:
        camera_delta += 0.25 * (after["camera"] - before["camera"])
        color_delta += 0.2 * (after["color"] - before["color"])
    if ending:
        architecture_delta += 0.2 * (after["architecture"] - before["architecture"])
        typography_delta += 0.2 * (after["typography"] - before["typography"])

    return {
        "color_flow_score": round(color_delta, 6),
        "architecture_flow_score": round(architecture_delta, 6),
        "camera_flow_score": round(camera_delta, 6),
        "saliency_flow_score": round(saliency_delta, 6),
        "typography_sequence_score": round(typography_delta, 6),
        "hidden_world_continuity_score": round(hidden_delta, 6),
        "storefront_opening_score": round(storefront_delta, 6),
        "character_consistency_score": round(character_delta, 6),
        "layout_search_support_score": round(layout_delta, 6),
        "weak_cluster_reduction_score": round(weak_delta, 6),
        "dual_audience_balance_score": round(dual_delta, 6),
        "page_turn_tension_summary_score": round(page_turn_delta, 6),
        "local_composite": round(after["local_composite"] - before["local_composite"], 6),
    }


def composite_delta(deltas: Dict[str, float]) -> float:
    weights = scoring_registry().local_candidate.sequence_optimizer_delta_weights
    return round(sum(float(deltas.get(k, 0.0) or 0.0) * w for k, w in weights.items()), 6)


def objective_delta(
    *,
    deltas: Dict[str, float],
    before_summary: Dict[str, float],
    weak_cluster_page: bool,
) -> float:
    weights = dict(scoring_registry().local_candidate.sequence_optimizer_delta_weights)
    total = 0.0
    for key, weight in weights.items():
        baseline = float(before_summary.get(key, 0.75) or 0.75)
        deficit_boost = 1.0 + (max(0.0, 0.75 - baseline) * 0.8)
        if weak_cluster_page and key in {"weak_cluster_reduction_score", "saliency_flow_score", "camera_flow_score"}:
            deficit_boost += 0.2
        total += float(deltas.get(key, 0.0) or 0.0) * weight * deficit_boost
    return round(total, 6)
