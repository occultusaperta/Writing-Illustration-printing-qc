from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np

from bookforge.saliency_flow.saliency import analyze_saliency_flow
from bookforge.scoring_registry import scoring_registry
from bookforge.saliency_flow.text_zones import score_text_zone_quietness
from bookforge.saliency_flow.types import (
    PageTurnFlowResult,
    SaliencyFlowScoreResult,
    SpreadBridgeResult,
    TextZoneQuietnessResult,
)


def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _zones(architecture_variant: Dict[str, Any] | None) -> Sequence[Dict[str, Any]]:
    if not architecture_variant:
        return []
    return [z for z in architecture_variant.get("zones", []) if isinstance(z, dict)]


def _point_in_zone(x: float, y: float, zone: Dict[str, Any]) -> bool:
    zx, zy = float(zone.get("x", 0.0)), float(zone.get("y", 0.0))
    zw, zh = float(zone.get("w", 0.0)), float(zone.get("h", 0.0))
    return zx <= x <= zx + zw and zy <= y <= zy + zh


def _score_primary_focus(first_fixation: Any, architecture_variant: Dict[str, Any] | None, shot_plan_entry: Dict[str, Any] | None, prompt_metadata: Dict[str, Any] | None) -> tuple[float, list[str], list[str]]:
    if first_fixation is None:
        return scoring_registry().saliency_flow.no_first_fixation_score, ["first_fixation_not_found"], []
    warnings: list[str] = []
    notes: list[str] = []
    zones = _zones(architecture_variant)
    art_zones = [z for z in zones if str(z.get("zone_type", "")).lower() in {"art", "inset"}]
    text_zones = [z for z in zones if str(z.get("zone_type", "")).lower() in {"text", "caption"}]

    in_art = any(_point_in_zone(first_fixation.x, first_fixation.y, z) for z in art_zones)
    in_text = any(_point_in_zone(first_fixation.x, first_fixation.y, z) for z in text_zones)
    base = 0.8 if in_art else 0.55
    if in_text:
        base -= 0.25
        warnings.append("first_fixation_text_dominant")

    shot_type = str((shot_plan_entry or {}).get("shot_type", ""))
    if shot_type == "closeup_emotion" and in_text:
        base -= 0.15
        warnings.append("closeup_emotion_focus_obscured_by_text_zone")
    elif shot_type == "establishing_wide" and first_fixation.strength < 0.35:
        warnings.append("establishing_wide_weak_entry_focus")

    guidance = ((prompt_metadata or {}).get("composition_guidance") or {}) if isinstance(prompt_metadata, dict) else {}
    fpoint = guidance.get("focal_point") if isinstance(guidance, dict) else None
    if isinstance(fpoint, (list, tuple)) and len(fpoint) == 2:
        fx, fy = float(fpoint[0]), float(fpoint[1])
        if fx > 1.0 or fy > 1.0:
            fx, fy = fx / 1024.0, fy / 1024.0
        dist = ((first_fixation.x - fx) ** 2 + (first_fixation.y - fy) ** 2) ** 0.5
        base = _clip01(base + max(-0.15, 0.18 - dist * 0.35))
    notes.append("primary_focus_scored_with_architecture_camera_prompt_context")
    return round(_clip01(base), 4), warnings, notes


def score_page_turn_flow(page_number: int | None, directional_energy: Dict[str, float], architecture_variant: Dict[str, Any] | None) -> PageTurnFlowResult:
    right = float(directional_energy.get("rightward_bias", 0.5) or 0.5)
    left = float(directional_energy.get("leftward_bias", 0.5) or 0.5)
    arch_type = str((architecture_variant or {}).get("architecture_type", ""))
    applicable = bool(page_number and page_number % 2 == 1) or arch_type in {"full_bleed_spread", "wordless_spread"}
    if not applicable:
        return PageTurnFlowResult(False, right, left, scoring_registry().saliency_flow.not_applicable_page_turn_score, [], ["page_turn_flow_not_applicable"])

    score = _clip01(0.5 + (right - left) * 0.55)
    warnings = ["page_turn_resistance_detected"] if score < 0.42 else []
    return PageTurnFlowResult(True, round(right, 4), round(left, 4), round(score, 4), warnings, [])


def score_spread_bridge(saliency_map: np.ndarray, architecture_variant: Dict[str, Any] | None) -> SpreadBridgeResult:
    arch_type = str((architecture_variant or {}).get("architecture_type", ""))
    applicable = arch_type in {"full_bleed_spread", "wordless_spread", "inset_composite"}
    if not applicable:
        return SpreadBridgeResult(False, 0.5, 0.0, 0.0, 0.0, 0.0, ["spread_bridge_not_applicable"])

    h, w = saliency_map.shape
    seam = max(1, int(w * 0.04))
    edge = max(1, int(w * 0.08))
    center = saliency_map[:, max(0, (w // 2) - seam):min(w, (w // 2) + seam)]
    left_edge = saliency_map[:, :edge]
    right_edge = saliency_map[:, w - edge:]

    gutter_energy = float(center.mean()) if center.size else 0.0
    le = float(left_edge.mean()) if left_edge.size else 0.0
    re = float(right_edge.mean()) if right_edge.size else 0.0
    bridge = _clip01(0.6 * min(1.0, (le + re) * 0.9) + 0.4 * min(1.0, gutter_energy * 1.2))
    gutter_risk = _clip01(max(0.0, gutter_energy - (le + re) * 0.35))
    warnings = []
    if bridge < 0.42:
        warnings.append("spread_bridge_weak")
    if gutter_risk > 0.5:
        warnings.append("critical_saliency_collapsing_into_gutter")
    return SpreadBridgeResult(True, round(bridge, 4), round(gutter_energy, 4), round(le, 4), round(re, 4), round(gutter_risk, 4), warnings)


def _score_fixation_order(flow: Any, text_quietness: TextZoneQuietnessResult) -> tuple[float, list[str]]:
    peaks = flow.peaks
    if not peaks:
        return scoring_registry().saliency_flow.no_fixation_order_score, ["fixation_order_unavailable"]
    top = peaks[0].strength
    second = peaks[1].strength if len(peaks) > 1 else 0.0
    separation = max(0.0, top - second)
    score = _clip01(0.45 + min(0.35, separation * 1.5) + 0.2 * text_quietness.quietness_score)
    warnings = ["fixation_order_ambiguous"] if separation < 0.06 else []
    return round(score, 4), warnings


def score_saliency_flow(
    image_path: Path | str,
    *,
    page_number: int | None = None,
    architecture_variant: Dict[str, Any] | None = None,
    shot_plan_entry: Dict[str, Any] | None = None,
    prompt_metadata: Dict[str, Any] | None = None,
) -> SaliencyFlowScoreResult:
    saliency_map, flow = analyze_saliency_flow(image_path)
    text_quietness = score_text_zone_quietness(saliency_map, _zones(architecture_variant))
    primary_focus_score, focus_warnings, focus_notes = _score_primary_focus(flow.first_fixation, architecture_variant, shot_plan_entry, prompt_metadata)
    page_turn = score_page_turn_flow(page_number, flow.directional_energy, architecture_variant)
    spread_bridge = score_spread_bridge(saliency_map, architecture_variant)
    fixation_order_score, fixation_warnings = _score_fixation_order(flow, text_quietness)

    warnings = list(flow.warnings) + focus_warnings + text_quietness.warnings + page_turn.warnings + spread_bridge.warnings + fixation_warnings
    notes = flow.notes + focus_notes

    weights = scoring_registry().saliency_flow.composite_weights
    composite = _clip01(
        weights["primary_focus"] * primary_focus_score
        + weights["text_quietness"] * text_quietness.quietness_score
        + weights["page_turn"] * page_turn.page_turn_flow_score
        + weights["spread_bridge"] * spread_bridge.bridge_score
        + weights["fixation_order"] * fixation_order_score
    )
    confidence = _clip01(0.45 + 0.35 * flow.confidence + 0.2 * (1.0 if flow.first_fixation else 0.0))

    return SaliencyFlowScoreResult(
        primary_focus_score=round(primary_focus_score, 4),
        text_quietness_score=round(text_quietness.quietness_score, 4),
        page_turn_flow_score=round(page_turn.page_turn_flow_score, 4),
        spread_bridge_score=round(spread_bridge.bridge_score, 4),
        fixation_order_score=round(fixation_order_score, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
        peak_summaries=flow.peaks,
    )
