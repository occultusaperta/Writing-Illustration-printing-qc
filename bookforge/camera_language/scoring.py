from __future__ import annotations

from typing import Any, Dict, List

from bookforge.camera_language.types import ShotScoreResult
from bookforge.scoring_registry import scoring_registry
from bookforge.utils import clamp01


def _focus_area_ratio(focus_box: Any) -> float:
    if not isinstance(focus_box, (list, tuple)) or len(focus_box) != 4:
        return scoring_registry().camera_language.default_focus_area_ratio
    try:
        x0, y0, x1, y1 = [float(v) for v in focus_box]
    except (TypeError, ValueError):
        return scoring_registry().camera_language.default_focus_area_ratio
    w = max(0.0, x1 - x0)
    h = max(0.0, y1 - y0)
    area = w * h
    if area <= 0:
        return scoring_registry().camera_language.default_focus_area_ratio
    return area if area <= 1.0 else min(1.0, area / (1024.0 * 1024.0))


def _distance_target_score(distance_class: str, focus_ratio: float) -> float:
    expected = scoring_registry().camera_language.distance_ranges
    lo, hi = expected.get(distance_class, (0.1, 0.6))
    if lo <= focus_ratio <= hi:
        return 1.0
    if focus_ratio < lo:
        return clamp01(1.0 - (lo - focus_ratio) * 3.5)
    return clamp01(1.0 - (focus_ratio - hi) * 3.5)


def _angle_score(angle_class: str, focus_box: Any) -> float:
    if not isinstance(focus_box, (list, tuple)) or len(focus_box) != 4:
        return scoring_registry().camera_language.default_angle_score
    try:
        _, y0, _, y1 = [float(v) for v in focus_box]
    except (TypeError, ValueError):
        return scoring_registry().camera_language.default_angle_score
    cy = (y0 + y1) / 2.0
    if cy > 1.0:
        cy = cy / 1024.0
    if angle_class == "high_angle":
        return clamp01(1.0 - abs(cy - 0.35) * 2.5)
    if angle_class == "low_angle":
        return clamp01(1.0 - abs(cy - 0.65) * 2.5)
    if angle_class == "tilted":
        return scoring_registry().camera_language.tilted_angle_score
    if angle_class == "over_shoulder":
        return scoring_registry().camera_language.over_shoulder_angle_score
    return clamp01(1.0 - abs(cy - 0.5) * 1.6)


def score_shot_adherence(variant_report: Dict[str, Any], shot_plan_entry: Dict[str, Any] | None) -> ShotScoreResult | None:
    if not shot_plan_entry:
        return None
    focus_box = variant_report.get("focus_box")
    focus_ratio = _focus_area_ratio(focus_box)
    distance_class = str(shot_plan_entry.get("target_distance_class", "medium"))
    angle_class = str(shot_plan_entry.get("target_angle_class", "level"))
    shot_type = str(shot_plan_entry.get("shot_type", "medium_interaction"))

    framing_score = _distance_target_score(distance_class, focus_ratio)
    focus_alignment = clamp01(1.0 - float(variant_report.get("focus_bleed_overlap", 0.0) or 0.0) * scoring_registry().camera_language.framing_focus_overlap_penalty)
    angle_alignment = _angle_score(angle_class, focus_box)

    family_match = 0.55 + 0.25 * framing_score + 0.2 * angle_alignment
    if shot_type == "dutch_tilt":
        family_match = min(1.0, family_match + 0.08)

    warnings: List[str] = []
    notes: List[str] = []
    if framing_score < 0.55:
        warnings.append("framing scale appears mismatched to planned shot distance")
    if angle_alignment < 0.5:
        warnings.append("camera angle proxy weakly aligned with planned shot")
    if focus_alignment < 0.5:
        warnings.append("subject focus overlaps safety zones or loses emphasis")
    if not warnings:
        notes.append("shot heuristics are broadly aligned with plan")

    weights = scoring_registry().camera_language.shot_weights
    composite = clamp01(weights["framing"] * framing_score + weights["focus"] * focus_alignment + weights["angle"] * angle_alignment + weights["family"] * family_match)
    confidence = 0.55 if angle_class in {"over_shoulder", "tilted"} else 0.7

    return ShotScoreResult(
        shot_type=shot_type,
        framing_scale_score=round(framing_score, 4),
        focus_alignment_score=round(focus_alignment, 4),
        angle_alignment_score=round(angle_alignment, 4),
        family_match_score=round(family_match, 4),
        composite_score=round(composite, 4),
        confidence=confidence,
        warnings=warnings,
        notes=notes,
    )
