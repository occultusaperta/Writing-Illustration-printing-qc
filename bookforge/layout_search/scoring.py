from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.layout_search.types import LayoutPermutation, LayoutPermutationScore
from bookforge.saliency_flow import score_saliency_flow


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _normalized_to_pixels(zone: Dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    x0 = int(max(0, min(width - 1, zone.get("x", 0.0) * width)))
    y0 = int(max(0, min(height - 1, zone.get("y", 0.0) * height)))
    x1 = int(max(x0 + 1, min(width, (zone.get("x", 0.0) + zone.get("w", 0.0)) * width)))
    y1 = int(max(y0 + 1, min(height, (zone.get("y", 0.0) + zone.get("h", 0.0)) * height)))
    return x0, y0, x1, y1


def _region_stats(image_path: Path, zone: Dict[str, float]) -> tuple[float, float]:
    with Image.open(image_path) as im:
        gray = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = gray.shape
    x0, y0, x1, y1 = _normalized_to_pixels(zone, w, h)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return 255.0, 0.0
    gx = np.zeros_like(crop)
    gy = np.zeros_like(crop)
    gx[:, 1:-1] = crop[:, 2:] - crop[:, :-2]
    gy[1:-1, :] = crop[2:, :] - crop[:-2, :]
    busy = float(np.mean(np.sqrt(gx * gx + gy * gy)))
    lum = float(np.mean(crop))
    return lum, busy


def score_layout_permutation(
    permutation: LayoutPermutation,
    *,
    image_path: Path,
    page_text: str,
    base_layout: Dict[str, Any],
    page_number: int,
    is_spread: bool,
    gutter_sensitive: bool,
) -> LayoutPermutationScore:
    warnings: List[str] = []
    notes: List[str] = []

    lum, busy = _region_stats(image_path, permutation.text_zone)
    contrast_pref = 1.0 - abs((lum / 255.0) - 0.5) * 1.2
    text_readability = _clamp01(0.65 * contrast_pref + 0.35 * (1.0 - min(1.0, busy / 60.0)))

    zone_area = max(0.001, permutation.text_zone["w"] * permutation.text_zone["h"])
    char_demand = max(1.0, len(page_text.strip()) / 240.0)
    text_fit = _clamp01(1.0 - max(0.0, char_demand - (zone_area * 10.0)) * 0.35)

    pseudo_variant = {
        "architecture_type": permutation.architecture_type,
        "zones": [
            {"zone_id": "art", "zone_type": "art", **permutation.art_zone},
            {"zone_id": "text", "zone_type": "text", **permutation.text_zone},
        ],
    }
    saliency = score_saliency_flow(image_path, page_number=page_number, architecture_variant=pseudo_variant)
    saliency_quietness = _clamp01(saliency.text_quietness_score)
    focal_balance = _clamp01(0.55 * saliency.primary_focus_score + 0.45 * (1.0 - saliency.spread_bridge_score if is_spread else saliency.primary_focus_score))
    page_turn_flow = _clamp01(saliency.page_turn_flow_score)

    gutter_mid = 0.5
    text_mid = permutation.text_zone["x"] + 0.5 * permutation.text_zone["w"]
    dist = abs(text_mid - gutter_mid)
    gutter_safety = _clamp01(0.2 + min(0.8, dist * 2.2)) if gutter_sensitive or is_spread else 1.0

    whitespace = max(0.0, 1.0 - (permutation.art_zone["w"] * permutation.art_zone["h"] + zone_area))
    whitespace_balance = _clamp01(1.0 - abs(whitespace - 0.16) * 3.2)

    base_text = base_layout.get("text_zone", permutation.text_zone)
    alignment_delta = abs(base_text.get("x", 0.0) - permutation.text_zone["x"]) + abs(base_text.get("y", 0.0) - permutation.text_zone["y"])
    architecture_alignment = _clamp01(1.0 - alignment_delta * 1.8)

    rejected = False
    if text_fit < 0.42:
        warnings.append("text_fit_below_threshold")
        rejected = True
    if gutter_safety < 0.35:
        warnings.append("gutter_safety_violation")
        rejected = True
    if permutation.text_zone["w"] < 0.16 or permutation.text_zone["h"] < 0.10:
        warnings.append("text_zone_too_small")
        rejected = True

    composite = _clamp01(
        0.18 * text_readability
        + 0.18 * text_fit
        + 0.15 * saliency_quietness
        + 0.12 * focal_balance
        + 0.12 * gutter_safety
        + 0.10 * whitespace_balance
        + 0.08 * architecture_alignment
        + 0.07 * page_turn_flow
    )
    confidence = _clamp01(0.45 + 0.35 * (1.0 - min(1.0, len(warnings) * 0.3)) + 0.2 * saliency.confidence)

    if rejected:
        notes.append("Hard rejection triggered by bounded layout constraints.")

    return LayoutPermutationScore(
        permutation_id=permutation.permutation_id,
        text_readability_score=round(text_readability, 4),
        text_fit_score=round(text_fit, 4),
        saliency_quietness_score=round(saliency_quietness, 4),
        focal_balance_score=round(focal_balance, 4),
        gutter_safety_score=round(gutter_safety, 4),
        whitespace_balance_score=round(whitespace_balance, 4),
        architecture_alignment_score=round(architecture_alignment, 4),
        page_turn_flow_score=round(page_turn_flow, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        rejected=rejected,
        warnings=warnings,
        notes=notes,
    )
