from __future__ import annotations

from typing import Any, Dict, List


def build_hidden_world_guidance(page_plan: Dict[str, Any] | None) -> Dict[str, Any]:
    page_plan = page_plan if isinstance(page_plan, dict) else {}
    return {
        "required_details": list(page_plan.get("required_details", []) if isinstance(page_plan.get("required_details", []), list) else []),
        "recurring_motifs": list(page_plan.get("recurring_motifs", []) if isinstance(page_plan.get("recurring_motifs", []), list) else []),
        "foreshadowing_hints": list(page_plan.get("foreshadowing_hints", []) if isinstance(page_plan.get("foreshadowing_hints", []), list) else []),
        "callback_hints": list(page_plan.get("callback_hints", []) if isinstance(page_plan.get("callback_hints", []), list) else []),
        "parent_reward_details": list(page_plan.get("parent_reward_details", []) if isinstance(page_plan.get("parent_reward_details", []), list) else []),
        "visibility_targets": dict(page_plan.get("visibility_targets", {}) if isinstance(page_plan.get("visibility_targets", {}), dict) else {}),
        "discoverable_not_dominant": bool(page_plan.get("discoverable_not_dominant", True)),
        "notes": list(page_plan.get("notes", []) if isinstance(page_plan.get("notes", []), list) else []),
    }


def build_hidden_world_prompt_lines(guidance: Dict[str, Any] | None) -> List[str]:
    guidance = guidance if isinstance(guidance, dict) else {}
    lines: List[str] = []
    required = [str(x).strip() for x in guidance.get("required_details", []) if str(x).strip()]
    motifs = [str(x).strip() for x in guidance.get("recurring_motifs", []) if str(x).strip()]
    parent_reward = [str(x).strip() for x in guidance.get("parent_reward_details", []) if str(x).strip()]
    foreshadow = [str(x).strip() for x in guidance.get("foreshadowing_hints", []) if str(x).strip()]
    callback = [str(x).strip() for x in guidance.get("callback_hints", []) if str(x).strip()]

    if required:
        lines.append("Required hidden details (must include): " + "; ".join(required) + ".")
    if motifs:
        lines.append("Recurring hidden motifs to preserve: " + "; ".join(motifs) + ".")
    if foreshadow:
        lines.append("Foreshadowing hints: " + "; ".join(foreshadow[:2]) + ".")
    if callback:
        lines.append("Callback hints: " + "; ".join(callback[:2]) + ".")
    if parent_reward:
        lines.append("Parent-reward background storytelling details: " + "; ".join(parent_reward[:2]) + ".")

    if required or motifs or foreshadow or callback or parent_reward:
        lines.append("Keep hidden details discoverable but not dominant; avoid top saliency peak placement for subtle details.")
        lines.append("Avoid text-zone and gutter-critical collision for hidden details that are important to recurrence.")
    return lines


def build_hidden_world_negative_lines(guidance: Dict[str, Any] | None) -> List[str]:
    guidance = guidance if isinstance(guidance, dict) else {}
    if not guidance:
        return []
    return [
        "Do not let hidden motifs overpower focal action or primary character readability.",
        "Do not place hidden details where printed text overlays must remain clean.",
    ]
