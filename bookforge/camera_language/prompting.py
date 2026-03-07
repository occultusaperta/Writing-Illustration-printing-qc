from __future__ import annotations

from typing import Any, Dict, List

from bookforge.camera_language.constants import SHOT_PROMPT_LINES
from bookforge.camera_language.types import ShotType


def build_camera_guidance(plan_entry: Dict[str, Any] | None) -> Dict[str, Any]:
    if not plan_entry:
        return {}
    shot = ShotType(str(plan_entry.get("shot_type", ShotType.MEDIUM_INTERACTION.value)))
    return {
        "shot_type": shot.value,
        "narrative_reason": str(plan_entry.get("narrative_reason", "")),
        "target_distance_class": str(plan_entry.get("target_distance_class", "medium")),
        "target_angle_class": str(plan_entry.get("target_angle_class", "level")),
        "target_subject_focus": str(plan_entry.get("target_subject_focus", "primary scene action")),
        "sequence_priority": float(plan_entry.get("sequence_priority", 0.5) or 0.5),
        "prompt_intent": SHOT_PROMPT_LINES[shot],
    }


def build_camera_prompt_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []
    return [
        f"Camera shot plan: {guidance.get('shot_type', 'medium_interaction')}.",
        f"Framing guidance: {guidance.get('prompt_intent', '')}.",
        f"Subject focus: {guidance.get('target_subject_focus', '')}.",
        f"Angle intent: {guidance.get('target_angle_class', 'level')} perspective.",
    ]


def build_camera_negative_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []
    negatives: List[str] = []
    shot_type = str(guidance.get("shot_type", ""))
    if shot_type in {ShotType.ESTABLISHING_WIDE.value, ShotType.BIRDS_EYE.value}:
        negatives.append("avoid tight crop that breaks establishing composition")
    if shot_type in {ShotType.CLOSEUP_EMOTION.value, ShotType.EXTREME_CLOSEUP_DETAIL.value}:
        negatives.append("avoid distant staging that hides emotional/read-detail intent")
    if shot_type == ShotType.DUTCH_TILT.value:
        negatives.append("avoid extreme tilt that causes readability problems")
    return negatives
