from __future__ import annotations

from typing import Any, Dict, List

from bookforge.hidden_world.types import HiddenWorldScoreResult


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def score_hidden_world_adherence(
    *,
    page_number: int,
    hidden_world_guidance: Dict[str, Any] | None,
    prompt_metadata: Dict[str, Any] | None,
    saliency_score: Dict[str, Any] | None,
    architecture_variant: Dict[str, Any] | None,
    illustration_notes: str,
) -> HiddenWorldScoreResult:
    hidden_world_guidance = hidden_world_guidance if isinstance(hidden_world_guidance, dict) else {}
    prompt_metadata = prompt_metadata if isinstance(prompt_metadata, dict) else {}
    saliency_score = saliency_score if isinstance(saliency_score, dict) else {}
    architecture_variant = architecture_variant if isinstance(architecture_variant, dict) else {}

    warnings: List[str] = []
    notes: List[str] = [
        "Hidden-world adherence is heuristic/metadata-first and does not guarantee exact object detection.",
        f"Scored on page {page_number} using prompt metadata + saliency + architecture proxies.",
    ]

    required = [str(x).strip() for x in hidden_world_guidance.get("required_details", []) if str(x).strip()]
    motifs = [str(x).strip() for x in hidden_world_guidance.get("recurring_motifs", []) if str(x).strip()]
    foreshadow = [str(x).strip() for x in hidden_world_guidance.get("foreshadowing_hints", []) if str(x).strip()]
    callback = [str(x).strip() for x in hidden_world_guidance.get("callback_hints", []) if str(x).strip()]
    parent_reward = [str(x).strip() for x in hidden_world_guidance.get("parent_reward_details", []) if str(x).strip()]

    required_presence = 0.95 if required else 0.7
    recurrence = _clip01(0.55 + 0.1 * min(3, len(motifs)))
    foreshadow_callback = _clip01(0.45 + 0.15 * min(2, len(foreshadow) + len(callback)))
    parent_reward_score = _clip01(0.4 + 0.2 * min(2, len(parent_reward)))

    text_zone_present = bool(architecture_variant.get("text_zone"))
    zones = architecture_variant.get("zones", []) if isinstance(architecture_variant.get("zones", []), list) else []
    if any(str(z.get("zone_type", "")).lower() in {"text", "caption"} for z in zones if isinstance(z, dict)):
        text_zone_present = True
    text_collision_risk = 0.25 if text_zone_present else 0.1

    saliency_composite = float(saliency_score.get("composite_score", 0.5) or 0.5)
    subtlety_score = _clip01(0.75 if saliency_composite >= 0.45 else 0.5)
    if saliency_composite < 0.25 and (required or motifs):
        warnings.append("Hidden details may be too invisible due to weak saliency organization.")

    if text_zone_present and (required or motifs):
        warnings.append("Text-zone collision risk inferred from architecture zones; verify final layout.")

    if not hidden_world_guidance:
        notes.append("No hidden-world guidance available; treated as safe bounded no-op.")
        required_presence = recurrence = subtlety_score = parent_reward_score = foreshadow_callback = 0.5

    composite = _clip01(
        0.24 * required_presence
        + 0.18 * recurrence
        + 0.16 * subtlety_score
        + 0.14 * parent_reward_score
        + 0.14 * foreshadow_callback
        + 0.14 * (1.0 - text_collision_risk)
    )
    confidence = _clip01(0.4 + 0.2 * bool(hidden_world_guidance) + 0.2 * bool(prompt_metadata) + 0.2 * bool(saliency_score))

    return HiddenWorldScoreResult(
        required_detail_presence_score=round(required_presence, 4),
        recurrence_consistency_score=round(recurrence, 4),
        subtlety_score=round(subtlety_score, 4),
        parent_reward_score=round(parent_reward_score, 4),
        foreshadowing_callback_score=round(foreshadow_callback, 4),
        text_collision_risk_score=round(text_collision_risk, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
    )
