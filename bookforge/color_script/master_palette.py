from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from bookforge.color_script.constants import EMOTION_COLOR_PROFILES, HARMONY_BY_EMOTION, TARGET_CONFIG
from bookforge.color_script.lab import LABColor, chroma, hue_to_lab
from bookforge.color_script.types import EmotionType, MasterPalette, PageEmotionAnalysis


def _wrap_hue(h: float) -> float:
    return h % 360.0


def _harmony_hues(base_hue: float, harmony: str) -> List[float]:
    if harmony == "complementary":
        return [_wrap_hue(base_hue), _wrap_hue(base_hue + 180)]
    if harmony == "split_complementary":
        return [_wrap_hue(base_hue), _wrap_hue(base_hue + 150), _wrap_hue(base_hue + 210)]
    if harmony == "triadic":
        return [_wrap_hue(base_hue), _wrap_hue(base_hue + 120), _wrap_hue(base_hue + 240)]
    if harmony == "monochromatic":
        return [_wrap_hue(base_hue), _wrap_hue(base_hue + 8), _wrap_hue(base_hue - 8)]
    return [_wrap_hue(base_hue - 20), _wrap_hue(base_hue), _wrap_hue(base_hue + 20)]


def detect_dominant_emotion(analyses: Iterable[PageEmotionAnalysis]) -> EmotionType:
    weights = Counter()
    for a in analyses:
        weights[a.emotion] += a.intensity
    return max(weights, key=weights.get) if weights else EmotionType.NEUTRAL


def generate_master_palette(analyses: List[PageEmotionAnalysis]) -> MasterPalette:
    dominant = detect_dominant_emotion(analyses)
    profile = EMOTION_COLOR_PROFILES[dominant]
    harmony = HARMONY_BY_EMOTION[dominant]
    mean_intensity = sum(a.intensity for a in analyses) / max(1, len(analyses))
    base_hue = _wrap_hue(profile.preferred_hue_center + (mean_intensity - 0.5) * profile.hue_spread)
    hues = _harmony_hues(base_hue, harmony.value)

    dominant_colors = [hue_to_lab(h, profile.target_lightness, profile.target_chroma).as_tuple() for h in hues]
    accent_l = max(TARGET_CONFIG["min_lightness"], min(TARGET_CONFIG["max_lightness"], profile.target_lightness + 8))
    accent_colors = [hue_to_lab(_wrap_hue(base_hue + 35), accent_l, profile.target_chroma + 10).as_tuple()]
    neutrals = [LABColor(92.0, 0.0, 0.0).as_tuple(), LABColor(24.0, 0.0, 0.0).as_tuple()]

    palette = MasterPalette(
        dominant_emotion=dominant,
        harmony=harmony,
        base_hue=round(base_hue, 4),
        dominant_colors_lab=[list(c) for c in dominant_colors],
        accent_colors_lab=[list(c) for c in accent_colors],
        neutrals_lab=[list(c) for c in neutrals],
    )
    validate_master_palette(palette)
    return palette


def validate_master_palette(palette: MasterPalette) -> None:
    if not palette.dominant_colors_lab:
        raise ValueError("Master palette requires dominant colors")
    for color in palette.dominant_colors_lab + palette.accent_colors_lab:
        if len(color) != 3:
            raise ValueError("LAB color entries must be length-3")
        l, a, b = color
        if l < TARGET_CONFIG["min_lightness"] or l > TARGET_CONFIG["max_lightness"]:
            raise ValueError("Palette lightness out of supported bounds")
        if chroma(LABColor(l, a, b)) > TARGET_CONFIG["max_chroma"] + 8:
            raise ValueError("Palette chroma too high for planning stage")
