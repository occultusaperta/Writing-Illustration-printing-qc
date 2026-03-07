from __future__ import annotations

from typing import Any, Dict, List


TEMPERATURE_HINTS = {
    "warm": "predominantly warm amber, honey, and golden tones",
    "cool": "low-key cool blue-purple nighttime palette",
    "neutral": "balanced neutral palette with controlled warmth",
}


def _temperature_bucket(value: float) -> str:
    if value >= 0.15:
        return "warm"
    if value <= -0.15:
        return "cool"
    return "neutral"


def _mood_descriptors(emotion: str, intensity: float) -> List[str]:
    base = {
        "joy": ["uplifting", "radiant", "welcoming"],
        "wonder": ["luminous", "curious", "expansive"],
        "calm": ["gentle", "quiet", "breathable"],
        "tension": ["uneasy", "shadowed", "compressed"],
        "sadness": ["soft", "subdued", "melancholic"],
        "courage": ["resolute", "steady", "hopeful"],
        "mystery": ["enigmatic", "layered", "twilit"],
        "neutral": ["storybook", "balanced", "clear"],
    }
    descriptors = list(base.get(str(emotion).lower(), ["storybook", "balanced", "clear"]))
    if intensity >= 0.75:
        descriptors.append("high-drama")
    elif intensity <= 0.35:
        descriptors.append("muted")
    return descriptors[:4]


def _lab_to_brief(lab: List[float]) -> str:
    if not isinstance(lab, list) or len(lab) < 3:
        return "L0/a0/b0"
    return f"L{round(float(lab[0]), 1)}/a{round(float(lab[1]), 1)}/b{round(float(lab[2]), 1)}"


def build_color_script_guidance(color_spec: Dict[str, Any] | None, emotion_analysis: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not color_spec:
        return {}

    emotion = str(color_spec.get("emotion", emotion_analysis.get("emotion", "neutral") if emotion_analysis else "neutral"))
    intensity = float(emotion_analysis.get("intensity", 0.5) if emotion_analysis else 0.5)
    narrative_function = str(color_spec.get("narrative_function", emotion_analysis.get("narrative_function", "rising_action") if emotion_analysis else "rising_action"))
    dominant_palette = [str(_lab_to_brief(c)) for c in color_spec.get("dominant_colors_lab", []) if isinstance(c, list)]
    accent_color = _lab_to_brief(color_spec.get("accent_color_lab", []))
    forbidden = [str(_lab_to_brief(c)) for c in color_spec.get("forbidden_colors_lab", []) if isinstance(c, list)]
    target_temperature = float(color_spec.get("target_temperature", 0.0))
    temp_bucket = _temperature_bucket(target_temperature)

    return {
        "emotion": emotion,
        "intensity": round(intensity, 4),
        "narrative_function": narrative_function,
        "dominant_palette": dominant_palette,
        "accent_color": accent_color,
        "target_lightness": float(color_spec.get("target_lightness", 50.0)),
        "target_chroma": float(color_spec.get("target_chroma", 25.0)),
        "target_temperature": target_temperature,
        "background_value_key": _lab_to_brief(color_spec.get("background_key_lab", [])),
        "mood_descriptors": _mood_descriptors(emotion, intensity),
        "forbidden_palette": forbidden,
        "palette_direction": TEMPERATURE_HINTS[temp_bucket],
        "accent_guidance": "muted gentle palette with sparse high-chroma accent" if intensity <= 0.45 else "allow restrained accent pops only on key focal details",
        "lighting_guidance": "soft low-contrast lighting" if intensity <= 0.45 else "higher contrast key lighting with controlled shadows",
    }


def build_color_prompt_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []
    lines = [
        f"Color script: {guidance.get('palette_direction', 'balanced neutral palette')}.",
        f"Mood descriptors: {', '.join(guidance.get('mood_descriptors', []))}.",
        f"Dominant palette LAB anchors: {', '.join(guidance.get('dominant_palette', []))}.",
        f"Accent usage: {guidance.get('accent_guidance', 'restrained accents')} (accent {guidance.get('accent_color', '')}).",
        f"Lighting target: {guidance.get('lighting_guidance', '')}; lightness {guidance.get('target_lightness', '')}, chroma {guidance.get('target_chroma', '')}.",
    ]
    return [line for line in lines if line]


def build_color_negative_lines(guidance: Dict[str, Any]) -> List[str]:
    if not guidance:
        return []
    negatives: List[str] = []
    forbidden = guidance.get("forbidden_palette", [])
    if forbidden:
        negatives.append(f"avoid forbidden palette contamination: {', '.join(forbidden)}")
    if str(guidance.get("emotion", "")).lower() in {"fear", "tension", "mystery"}:
        negatives.append("avoid strong warm contamination in this fear beat")
    return negatives
