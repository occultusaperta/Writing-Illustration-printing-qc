from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.character_scoring.types import SilhouetteScoreResult


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _load_rgb(path: str | Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def _extract_subject_mask(arr: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    edge = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :])) + np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    edge_thr = float(np.quantile(edge, 0.68))
    lum_thr = float(np.quantile(gray, 0.4))

    edge_mask = edge > max(edge_thr, 2.5)
    lum_mask = gray < max(20.0, lum_thr)
    mask = np.logical_or(edge_mask, lum_mask)

    h, w = gray.shape
    y0, y1 = int(h * 0.15), int(h * 0.95)
    x0, x1 = int(w * 0.05), int(w * 0.95)
    roi = np.zeros_like(mask)
    roi[y0:y1, x0:x1] = True
    mask = np.logical_and(mask, roi)

    if float(mask.mean()) < 0.01:
        high_sat = np.max(arr, axis=2) - np.min(arr, axis=2)
        mask = np.logical_and(high_sat > np.quantile(high_sat, 0.75), roi)

    return mask, {
        "edge_threshold": edge_thr,
        "luminance_threshold": lum_thr,
    }


def score_character_silhouette(image_path: str | Path) -> SilhouetteScoreResult:
    arr = _load_rgb(image_path)
    h, w, _ = arr.shape
    mask, raw_diag = _extract_subject_mask(arr)

    warnings: list[str] = []
    notes: list[str] = ["Silhouette uses bounded proxy extraction; no landmark/segmentation model is assumed."]

    occupancy = float(mask.mean())
    if occupancy < 0.02:
        warnings.append("Subject silhouette extraction is weak; confidence reduced.")

    ys, xs = np.where(mask)
    if len(xs) == 0:
        return SilhouetteScoreResult(
            subject_occupancy=0.0,
            compactness_score=0.0,
            edge_complexity_score=0.0,
            distinguishability_score=0.0,
            iconic_readability_score=0.0,
            composite_score=0.0,
            confidence=0.05,
            warnings=warnings + ["Unable to derive silhouette proxy from candidate image."],
            notes=notes,
            diagnostics={**raw_diag, "area_px": 0.0, "perimeter_px": 0.0},
        )

    y_min, y_max = int(ys.min()), int(ys.max())
    x_min, x_max = int(xs.min()), int(xs.max())
    box_h = max(1, y_max - y_min + 1)
    box_w = max(1, x_max - x_min + 1)

    area = float(mask.sum())
    vert_transitions = np.count_nonzero(mask[1:, :] != mask[:-1, :])
    hor_transitions = np.count_nonzero(mask[:, 1:] != mask[:, :-1])
    perimeter = float(vert_transitions + hor_transitions)

    compactness = _clamp01((4.0 * math.pi * area) / max(perimeter * perimeter, 1.0))
    transition_density = perimeter / max(area, 1.0)
    edge_complexity_score = _clamp01(1.0 - abs(transition_density - 0.17) / 0.2)

    bbox_fill = area / float(box_h * box_w)
    aspect = box_w / max(float(box_h), 1.0)
    aspect_score = _clamp01(1.0 - abs(aspect - 0.75) / 0.95)
    distinguishability = _clamp01(0.45 * bbox_fill + 0.35 * aspect_score + 0.2 * (1.0 - abs(occupancy - 0.34) / 0.34))

    iconic = _clamp01(0.45 * compactness + 0.35 * edge_complexity_score + 0.2 * distinguishability)
    composite = _clamp01(0.35 * compactness + 0.3 * edge_complexity_score + 0.35 * distinguishability)

    if edge_complexity_score < 0.3:
        warnings.append("Silhouette may be too noisy or brittle for iconic readability/plush translation.")
    if distinguishability < 0.35:
        warnings.append("Silhouette reads as generic or low-distinctiveness in proxy scoring.")
    if occupancy > 0.75:
        warnings.append("Subject occupancy is very high; icon-like contour readability may be reduced.")

    confidence = _clamp01(0.2 + min(0.6, occupancy * 1.4) + min(0.2, box_h / max(h, 1) * 0.2))

    return SilhouetteScoreResult(
        subject_occupancy=round(occupancy, 4),
        compactness_score=round(compactness, 4),
        edge_complexity_score=round(edge_complexity_score, 4),
        distinguishability_score=round(distinguishability, 4),
        iconic_readability_score=round(iconic, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
        diagnostics={
            **raw_diag,
            "area_px": round(area, 2),
            "perimeter_px": round(perimeter, 2),
            "bbox_width_px": float(box_w),
            "bbox_height_px": float(box_h),
            "bbox_fill": round(float(bbox_fill), 4),
            "aspect_ratio": round(float(aspect), 4),
        },
    )
