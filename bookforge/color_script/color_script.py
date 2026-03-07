from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import json

from bookforge.color_script.constants import EMOTION_COLOR_PROFILES, TARGET_CONFIG
from bookforge.color_script.emotion_analysis import analyze_page_emotions
from bookforge.color_script.lab import LABColor, temperature_proxy
from bookforge.color_script.master_palette import generate_master_palette
from bookforge.color_script.types import PageColorSpec, PageEmotionAnalysis, TransitionSpec, as_jsonable, to_primitive


def generate_page_color_script(analyses: List[PageEmotionAnalysis], palette) -> tuple[List[PageColorSpec], List[TransitionSpec]]:
    specs: List[PageColorSpec] = []
    transitions: List[TransitionSpec] = []

    for idx, analysis in enumerate(analyses):
        profile = EMOTION_COLOR_PROFILES[analysis.emotion]
        lightness = max(TARGET_CONFIG["min_lightness"], min(TARGET_CONFIG["max_lightness"], profile.target_lightness + (analysis.intensity - 0.5) * 12))
        color = palette.dominant_colors_lab[idx % len(palette.dominant_colors_lab)]
        accent = palette.accent_colors_lab[idx % len(palette.accent_colors_lab)]
        temp = temperature_proxy(LABColor(*color))
        contrast = max(TARGET_CONFIG["min_page_contrast"], min(TARGET_CONFIG["max_page_contrast"], TARGET_CONFIG["default_page_contrast"] + (analysis.intensity - 0.5) * 0.2))
        spec = PageColorSpec(
            page_number=analysis.page_number,
            emotion=analysis.emotion,
            target_lightness=round(lightness, 4),
            target_chroma=round(profile.target_chroma, 4),
            target_temperature=round(temp, 4),
            target_contrast=round(contrast, 4),
            dominant_colors_lab=[list(color)],
            accent_color_lab=list(accent),
            forbidden_colors_lab=[list(n) for n in palette.neutrals_lab if n[0] < 28],
            background_key_lab=list(palette.neutrals_lab[0]),
            narrative_function=analysis.narrative_function,
        )
        specs.append(spec)
        if idx > 0:
            delta_i = abs(analysis.intensity - analyses[idx - 1].intensity)
            transitions.append(
                TransitionSpec(
                    from_page=analyses[idx - 1].page_number,
                    to_page=analysis.page_number,
                    mode="hard_cut" if delta_i > TARGET_CONFIG["transition_threshold"] else "blend",
                    strength=round(min(1.0, 0.25 + delta_i), 4),
                )
            )
    return specs, transitions


def plan_color_script(pages: List[Dict[str, object]]) -> Tuple[List[PageEmotionAnalysis], object, List[PageColorSpec], List[TransitionSpec]]:
    analyses = analyze_page_emotions(pages)
    palette = generate_master_palette(analyses)
    page_specs, transitions = generate_page_color_script(analyses, palette)
    return analyses, palette, page_specs, transitions


def write_planning_artifacts(base_dir: Path, analyses: List[PageEmotionAnalysis], palette, page_specs: List[PageColorSpec], transitions: List[TransitionSpec]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "emotion_analysis.json").write_text(json.dumps(as_jsonable(analyses), indent=2), encoding="utf-8")
    (base_dir / "master_palette.json").write_text(json.dumps(to_primitive(palette), indent=2), encoding="utf-8")
    (base_dir / "color_script.json").write_text(json.dumps({"pages": as_jsonable(page_specs), "transitions": as_jsonable(transitions)}, indent=2), encoding="utf-8")
