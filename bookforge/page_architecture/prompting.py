from __future__ import annotations

from typing import Any, Dict, List


ARCHITECTURE_INTENTS = {
    "full_bleed_spread": {"framing": "strong establishing shot", "spread_mode": "spread", "text_strategy": "minimal_text"},
    "wordless_spread": {"framing": "cinematic reveal composition", "spread_mode": "spread", "text_strategy": "wordless"},
    "full_bleed_single": {"framing": "single-page immersive framing", "spread_mode": "single", "text_strategy": "caption_support"},
    "vignette": {"framing": "vignette composition with generous whitespace", "spread_mode": "single", "text_strategy": "quiet_text_zone"},
    "spot_illustration": {"framing": "centered subject grouping", "spread_mode": "single", "text_strategy": "text_forward"},
    "panel_sequence": {"framing": "panel sequence showing staged action beats", "spread_mode": "single", "text_strategy": "caption_panels"},
    "text_dominant": {"framing": "quiet composition preserving reading flow", "spread_mode": "single", "text_strategy": "text_dominant"},
    "inset_composite": {"framing": "base scene with inset callouts", "spread_mode": "single", "text_strategy": "inset_captions"},
}


def _camera_intent(narrative_function: str, architecture_type: str, target_energy: float) -> str:
    fn = str(narrative_function).lower()
    if architecture_type in {"full_bleed_spread", "wordless_spread"}:
        return "establishing wide shot"
    if fn in {"climax", "reveal"}:
        return "reveal composition"
    if fn in {"conflict", "tension", "rising_action"} and target_energy >= 0.65:
        return "low-angle intimidation"
    if fn in {"resolution", "falling_action", "calm"}:
        return "intimate calm framing"
    if target_energy <= 0.4:
        return "emotional close-up"
    return "medium interaction shot"


def _zone_hints(zones: List[Dict[str, Any]]) -> List[str]:
    hints: List[str] = []
    for z in zones:
        zone_id = str(z.get("zone_id", "zone"))
        zone_type = str(z.get("zone_type", "art"))
        if zone_type in {"text", "caption"}:
            hints.append(f"keep {zone_id} quiet for text")
        elif zone_type == "inset":
            hints.append(f"reserve {zone_id} for inset storytelling")
        elif zone_type == "bleed_guard":
            hints.append(f"respect {zone_id} margins for trim safety")
    return hints


def build_page_architecture_guidance(plan: Dict[str, Any] | None, variant: Dict[str, Any] | None) -> Dict[str, Any]:
    if not plan:
        return {}

    architecture_type = str(plan.get("selected_architecture_type", "full_bleed_single"))
    target_energy = float(plan.get("target_energy", 0.5))
    narrative_function = str(plan.get("narrative_function", "rising_action"))
    intent = ARCHITECTURE_INTENTS.get(architecture_type, ARCHITECTURE_INTENTS["full_bleed_single"])
    zones = variant.get("zones", []) if isinstance(variant, dict) else []
    spread_mode = str(intent.get("spread_mode", "single"))
    gutter_required = spread_mode == "spread"

    return {
        "architecture_type": architecture_type,
        "variant_id": str(plan.get("selected_variant_id", "")),
        "target_energy": round(target_energy, 4),
        "camera_intent": _camera_intent(narrative_function, architecture_type, target_energy),
        "framing_intent": str(intent.get("framing", "storybook framing")),
        "text_strategy": str(intent.get("text_strategy", "caption_support")),
        "zone_hints": _zone_hints(zones),
        "gutter_safety_required": gutter_required,
        "spread_mode": spread_mode,
    }


def build_architecture_prompt_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []

    lines = [
        f"Page architecture: {guidance.get('architecture_type', '')} ({guidance.get('variant_id', '')}).",
        f"Composition intent: {guidance.get('framing_intent', '')}; camera intent {guidance.get('camera_intent', '')}.",
        f"Layout mode: {'full-bleed spread' if guidance.get('spread_mode') == 'spread' else 'single-page oriented'}.",
        f"Text strategy: {guidance.get('text_strategy', '')}.",
    ]
    zone_hints = guidance.get("zone_hints", [])
    if zone_hints:
        lines.append(f"Zone hints: {'; '.join(zone_hints)}.")
    if guidance.get("gutter_safety_required"):
        lines.append("Keep central gutter free of critical facial detail and key subject anatomy.")
    return [line for line in lines if line]


def build_architecture_negative_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []
    negatives: List[str] = []
    if guidance.get("zone_hints"):
        negatives.append("avoid busy text zones")
    if guidance.get("gutter_safety_required"):
        negatives.append("avoid critical subject placement in gutter-danger zone")
    arch = str(guidance.get("architecture_type", ""))
    if arch == "panel_sequence":
        negatives.append("avoid merged single-scene composition that conflicts with panel-sequence intent")
    if arch == "text_dominant":
        negatives.append("avoid dense background clutter that conflicts with text-dominant page intent")
    return negatives
