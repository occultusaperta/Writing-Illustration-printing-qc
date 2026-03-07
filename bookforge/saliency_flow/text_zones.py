from __future__ import annotations

from typing import Any, Dict, Sequence

import numpy as np

from bookforge.saliency_flow.types import TextZoneQuietnessResult


def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _zone_slice(arr: np.ndarray, zone: Dict[str, Any]) -> np.ndarray:
    h, w = arr.shape[:2]
    x0 = int(np.clip(float(zone.get("x", 0.0)) * w, 0, w - 1))
    y0 = int(np.clip(float(zone.get("y", 0.0)) * h, 0, h - 1))
    x1 = int(np.clip((float(zone.get("x", 0.0)) + float(zone.get("w", 0.0))) * w, x0 + 1, w))
    y1 = int(np.clip((float(zone.get("y", 0.0)) + float(zone.get("h", 0.0))) * h, y0 + 1, h))
    return arr[y0:y1, x0:x1]


def score_text_zone_quietness(saliency_map: np.ndarray, zones: Sequence[Dict[str, Any]] | None) -> TextZoneQuietnessResult:
    text_zones = [z for z in (zones or []) if str(z.get("zone_type", "")).lower() in {"text", "caption"}]
    if not text_zones:
        return TextZoneQuietnessResult(False, 0.0, 0.0, 1.0, ["no_text_zone_declared"])

    means = []
    for z in text_zones:
        crop = _zone_slice(saliency_map, z)
        means.append(float(crop.mean()) if crop.size else 0.0)

    text_mean = float(np.mean(means)) if means else 0.0
    overall = float(saliency_map.mean())
    surrounding = max(0.0, float((overall * 1.15) - (text_mean * 0.15)))
    quietness = _clip01(1.0 - (0.72 * text_mean + 0.28 * max(0.0, text_mean - surrounding)))
    warnings = []
    if text_mean > 0.48:
        warnings.append("text_zone_saliency_busy")
    return TextZoneQuietnessResult(
        text_zone_present=True,
        mean_saliency=round(_clip01(text_mean), 4),
        surrounding_mean_saliency=round(_clip01(surrounding), 4),
        quietness_score=round(quietness, 4),
        warnings=warnings,
    )
