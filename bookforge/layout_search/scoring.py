from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.layout_search.types import LayoutPermutation, LayoutPermutationScore
from bookforge.saliency_flow import score_saliency_flow
from bookforge.utils import clamp01


_GUTTER_PADDING = 0.03


def _normalized_to_pixels(zone: Dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    x0 = int(max(0, min(width - 1, zone.get("x", 0.0) * width)))
    y0 = int(max(0, min(height - 1, zone.get("y", 0.0) * height)))
    x1 = int(max(x0 + 1, min(width, (zone.get("x", 0.0) + zone.get("w", 0.0)) * width)))
    y1 = int(max(y0 + 1, min(height, (zone.get("y", 0.0) + zone.get("h", 0.0)) * height)))
    return x0, y0, x1, y1


def _region_stats(image_path: Path, zone: Dict[str, float]) -> tuple[float, float, float]:
    with Image.open(image_path) as im:
        gray = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = gray.shape
    x0, y0, x1, y1 = _normalized_to_pixels(zone, w, h)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return 255.0, 0.0, 0.0
    gx = np.zeros_like(crop)
    gy = np.zeros_like(crop)
    gx[:, 1:-1] = crop[:, 2:] - crop[:, :-2]
    gy[1:-1, :] = crop[2:, :] - crop[:-2, :]
    busy = float(np.mean(np.sqrt(gx * gx + gy * gy)))
    lum = float(np.mean(crop))
    var = float(np.std(crop))
    return lum, busy, var


def _intersection_area(a: Dict[str, float], b: Dict[str, float]) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    return ix * iy


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
    rejection_reasons: List[str] = []
    notes: List[str] = []

    lum, busy, var = _region_stats(image_path, permutation.text_zone)
    contrast_pref = 1.0 - abs((lum / 255.0) - 0.47) * 1.15
    texture_penalty = min(1.0, busy / 55.0)
    noise_penalty = min(1.0, var / 75.0)
    text_readability = clamp01(0.58 * contrast_pref + 0.28 * (1.0 - texture_penalty) + 0.14 * (1.0 - noise_penalty))

    zone_area = max(0.001, permutation.text_zone["w"] * permutation.text_zone["h"])
    char_count = len(page_text.strip())
    char_demand = max(1.0, char_count / 220.0)
    effective_capacity = zone_area * 11.0
    overflow = max(0.0, char_demand - effective_capacity)
    text_fit = clamp01(1.0 - overflow * 0.38)

    pseudo_variant = {
        "architecture_type": permutation.architecture_type,
        "zones": [
            {"zone_id": "art", "zone_type": "art", **permutation.art_zone},
            {"zone_id": "text", "zone_type": "text", **permutation.text_zone},
        ],
    }
    saliency = score_saliency_flow(image_path, page_number=page_number, architecture_variant=pseudo_variant)
    saliency_quietness = clamp01(saliency.text_quietness_score)
    focal_balance = clamp01(0.60 * saliency.primary_focus_score + 0.40 * (1.0 - saliency.spread_bridge_score if is_spread else saliency.primary_focus_score))
    page_turn_flow = clamp01(saliency.page_turn_flow_score)

    text_mid = permutation.text_zone["x"] + 0.5 * permutation.text_zone["w"]
    left_edge = permutation.text_zone["x"]
    right_edge = permutation.text_zone["x"] + permutation.text_zone["w"]
    dist_mid = abs(text_mid - 0.5)
    inset_from_gutter = min(abs(left_edge - 0.5), abs(right_edge - 0.5))
    gutter_safety = 1.0
    if gutter_sensitive or is_spread:
        gutter_safety = clamp01(0.10 + min(0.75, dist_mid * 2.0) + min(0.15, max(0.0, inset_from_gutter - 0.015) * 5.0))

    whitespace = max(0.0, 1.0 - (permutation.art_zone["w"] * permutation.art_zone["h"] + zone_area - _intersection_area(permutation.art_zone, permutation.text_zone)))
    whitespace_balance = clamp01(1.0 - abs(whitespace - 0.18) * 3.1)

    base_text = base_layout.get("text_zone", permutation.text_zone)
    alignment_delta = abs(base_text.get("x", 0.0) - permutation.text_zone["x"]) + abs(base_text.get("y", 0.0) - permutation.text_zone["y"])
    size_delta = abs(base_text.get("w", 0.0) - permutation.text_zone["w"]) + abs(base_text.get("h", 0.0) - permutation.text_zone["h"])
    architecture_alignment = clamp01(1.0 - alignment_delta * 1.25 - size_delta * 0.55)

    if text_fit < 0.45:
        warnings.append("text_fit_below_threshold")
        rejection_reasons.append("text_fit_below_threshold")
    if gutter_safety < 0.40:
        warnings.append("gutter_safety_violation")
        rejection_reasons.append("gutter_safety_violation")
    if permutation.text_zone["w"] < 0.16 or permutation.text_zone["h"] < 0.10:
        warnings.append("text_zone_too_small")
        rejection_reasons.append("text_zone_too_small")
    if (gutter_sensitive or is_spread) and (left_edge < 0.5 < right_edge) and min(abs(0.5 - left_edge), abs(right_edge - 0.5)) < _GUTTER_PADDING:
        warnings.append("text_zone_crosses_gutter_unsafe")
        rejection_reasons.append("text_zone_crosses_gutter_unsafe")

    rejected = bool(rejection_reasons)

    composite = clamp01(
        0.20 * text_readability
        + 0.20 * text_fit
        + 0.12 * saliency_quietness
        + 0.10 * focal_balance
        + 0.16 * gutter_safety
        + 0.12 * whitespace_balance
        + 0.07 * architecture_alignment
        + 0.03 * page_turn_flow
    )
    confidence = clamp01(0.48 + 0.34 * (1.0 - min(1.0, len(rejection_reasons) * 0.4)) + 0.18 * saliency.confidence)

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
        rejection_reasons=rejection_reasons,
        notes=notes,
    )
