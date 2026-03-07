from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.color_script.lab import LABColor, lab_to_srgb, srgb_to_lab
from bookforge.color_script.scoring import (
    ColorScoreResult,
    compute_color_composite_score,
    extract_image_color_profile,
    score_color_adherence,
)

_ACTION_ORDER = [
    "lightness_shift",
    "contrast_lift",
    "temperature_shift",
    "saturation_adjust",
    "shadow_balance",
]
_MAX_ACTIONS = 3
_SKIP_COMPOSITE_THRESHOLD = 0.92


@dataclass(frozen=True)
class PostProcessResult:
    corrected_image: Image.Image
    actions_applied: List[str]
    delta_scores_estimate: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _to_image(image: Image.Image | np.ndarray | Path | str) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, np.ndarray):
        return Image.fromarray(image.astype(np.uint8), mode="RGB")
    with Image.open(image) as im:
        return im.convert("RGB")


def _rgb_to_lab_array(rgb: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 3)
    lab = np.asarray([srgb_to_lab((int(px[0]), int(px[1]), int(px[2]))).as_tuple() for px in flat], dtype=np.float32)
    return lab.reshape(rgb.shape)


def _lab_to_rgb_array(lab: np.ndarray) -> np.ndarray:
    flat = lab.reshape(-1, 3)
    rgb = np.asarray([lab_to_srgb(LABColor(float(px[0]), float(px[1]), float(px[2]))) for px in flat], dtype=np.uint8)
    return rgb.reshape(lab.shape)


def _canonical_actions(hints: List[str]) -> List[str]:
    aliases = {
        "lightness_tune": "lightness_shift",
        "temperature_rebalance": "temperature_shift",
        "chroma_tune": "saturation_adjust",
    }
    normalized = [aliases.get(action, action) for action in hints]
    ordered = [a for a in _ACTION_ORDER if a in normalized]
    return ordered[:_MAX_ACTIONS]


def _apply_lightness_shift(lab: np.ndarray, color_score: ColorScoreResult, page_spec: Dict[str, Any]) -> np.ndarray:
    target = float(page_spec.get("target_lightness", color_score.measured_lightness))
    delta = float(np.clip(target - color_score.measured_lightness, -10.0, 10.0))
    out = lab.copy()
    out[:, :, 0] = np.clip(out[:, :, 0] + delta, 0.0, 100.0)
    return out


def _apply_contrast_lift(lab: np.ndarray, color_score: ColorScoreResult, page_spec: Dict[str, Any]) -> np.ndarray:
    target = float(page_spec.get("target_contrast", color_score.measured_contrast))
    if target <= color_score.measured_contrast:
        factor = 1.0
    else:
        delta = min(0.15, max(0.0, (target - color_score.measured_contrast) * 0.8))
        factor = 1.0 + delta
    l_chan = lab[:, :, 0]
    mean = float(np.mean(l_chan))
    out = lab.copy()
    out[:, :, 0] = np.clip(((l_chan - mean) * factor) + mean, 0.0, 100.0)
    return out


def _apply_temperature_shift(lab: np.ndarray, color_score: ColorScoreResult, page_spec: Dict[str, Any]) -> np.ndarray:
    target = float(page_spec.get("target_temperature", color_score.measured_temperature))
    delta = float(np.clip((target - color_score.measured_temperature) * 64.0, -8.0, 8.0))
    out = lab.copy()
    out[:, :, 1] = np.clip(out[:, :, 1] + delta, -128.0, 127.0)
    out[:, :, 2] = np.clip(out[:, :, 2] + delta, -128.0, 127.0)
    return out


def _apply_saturation_adjust(lab: np.ndarray, color_score: ColorScoreResult, page_spec: Dict[str, Any]) -> np.ndarray:
    target = float(page_spec.get("target_chroma", color_score.measured_chroma))
    if color_score.measured_chroma <= 1e-6:
        factor = 1.0
    else:
        factor = float(np.clip(target / color_score.measured_chroma, 0.88, 1.12))
    out = lab.copy()
    out[:, :, 1] = np.clip(out[:, :, 1] * factor, -128.0, 127.0)
    out[:, :, 2] = np.clip(out[:, :, 2] * factor, -128.0, 127.0)
    return out


def _apply_shadow_balance(rgb: np.ndarray, color_score: ColorScoreResult, page_spec: Dict[str, Any]) -> np.ndarray:
    target = float(page_spec.get("target_lightness", color_score.measured_lightness))
    gamma = float(np.clip(1.0 + ((color_score.measured_lightness - target) / 100.0), 0.9, 1.1))
    normalized = np.clip(rgb.astype(np.float32) / 255.0, 0.0, 1.0)
    corrected = np.power(normalized, gamma)
    return np.clip(corrected * 255.0, 0.0, 255.0).astype(np.uint8)


def apply_color_postprocess(
    image: Image.Image | np.ndarray | Path | str,
    color_score: ColorScoreResult,
    page_spec: Dict[str, Any] | None,
) -> PostProcessResult:
    page_spec = page_spec or {}
    source_image = _to_image(image)

    if color_score.composite_score >= _SKIP_COMPOSITE_THRESHOLD:
        return PostProcessResult(source_image, [], {"original_composite": color_score.composite_score, "new_composite": color_score.composite_score, "composite_delta": 0.0})

    actions = _canonical_actions(color_score.post_process_actions)
    if not actions:
        return PostProcessResult(source_image, [], {"original_composite": color_score.composite_score, "new_composite": color_score.composite_score, "composite_delta": 0.0})

    rgb = np.asarray(source_image.convert("RGB"), dtype=np.uint8)
    lab = _rgb_to_lab_array(rgb)
    for action in actions:
        if action == "lightness_shift":
            lab = _apply_lightness_shift(lab, color_score, page_spec)
        elif action == "contrast_lift":
            lab = _apply_contrast_lift(lab, color_score, page_spec)
        elif action == "temperature_shift":
            lab = _apply_temperature_shift(lab, color_score, page_spec)
        elif action == "saturation_adjust":
            lab = _apply_saturation_adjust(lab, color_score, page_spec)
        elif action == "shadow_balance":
            rgb = _lab_to_rgb_array(lab)
            rgb = _apply_shadow_balance(rgb, color_score, page_spec)
            lab = _rgb_to_lab_array(rgb)

    corrected_rgb = _lab_to_rgb_array(lab)
    corrected_image = Image.fromarray(corrected_rgb, mode="RGB")

    master_palette = page_spec.get("_master_palette") if isinstance(page_spec.get("_master_palette"), dict) else None
    corrected_profile = extract_image_color_profile(corrected_image)
    corrected_adherence = score_color_adherence(corrected_profile, page_spec, master_palette, image=corrected_image)
    new_composite = compute_color_composite_score(corrected_adherence)
    if new_composite < color_score.composite_score:
        return PostProcessResult(
            source_image,
            [],
            {
                "original_composite": color_score.composite_score,
                "new_composite": new_composite,
                "composite_delta": new_composite - color_score.composite_score,
                "aborted": 1.0,
            },
        )

    return PostProcessResult(
        corrected_image,
        actions,
        {
            "original_composite": color_score.composite_score,
            "new_composite": new_composite,
            "composite_delta": new_composite - color_score.composite_score,
        },
    )
