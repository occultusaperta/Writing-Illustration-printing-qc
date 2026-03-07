from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.character_scoring.types import BabySchemaScoreResult


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _load_rgb(path: str | Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def score_baby_schema(image_path: str | Path, *, generalized_mode: bool = True) -> BabySchemaScoreResult:
    arr = _load_rgb(image_path)
    h, w, _ = arr.shape
    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    y_mid = int(h * 0.5)
    top = gray[:y_mid, :]
    bottom = gray[y_mid:, :]

    top_var = float(np.std(top))
    bottom_var = float(np.std(bottom))
    top_dark = float((top < np.quantile(gray, 0.22)).mean())
    top_edge = float((np.abs(np.diff(top, axis=1, prepend=top[:, :1])) > 8).mean())

    sat = np.max(arr, axis=2) - np.min(arr, axis=2)
    soft_patch = gray[int(h * 0.12):int(h * 0.55), int(w * 0.2):int(w * 0.8)]
    soft_grad = np.mean(np.abs(np.diff(soft_patch, axis=0, prepend=soft_patch[:1, :])) + np.abs(np.diff(soft_patch, axis=1, prepend=soft_patch[:, :1])))

    head_to_body_ratio_score = _clamp01(0.35 + (top_var / max(bottom_var + 1e-6, 1.0)) * 0.4)
    eye_prominence_score = _clamp01(0.2 + 2.6 * top_dark + 0.8 * top_edge)

    bright_mask = gray > np.quantile(gray, 0.55)
    ys, xs = np.where(bright_mask)
    if len(xs) > 0:
        bx = float(xs.max() - xs.min() + 1)
        by = float(ys.max() - ys.min() + 1)
        roundness_proxy = (4.0 * math.pi * float(bright_mask.sum())) / max((2.0 * (bx + by)) ** 2, 1.0)
    else:
        roundness_proxy = 0.1
    face_roundness_score = _clamp01(roundness_proxy * 2.5)

    cheek_fullness_or_softness_score = _clamp01(1.0 - soft_grad / 34.0)

    low_sat_ratio = float((sat < np.quantile(sat, 0.6)).mean())
    vertical_extent = float((gray < np.quantile(gray, 0.4)).mean())
    limb_shortness_softness_score = _clamp01(0.55 * low_sat_ratio + 0.45 * (1.0 - vertical_extent))

    overall = _clamp01(
        0.24 * head_to_body_ratio_score
        + 0.22 * eye_prominence_score
        + 0.18 * face_roundness_score
        + 0.2 * cheek_fullness_or_softness_score
        + 0.16 * limb_shortness_softness_score
    )
    composite = _clamp01(0.7 * overall + 0.3 * face_roundness_score)

    warnings: list[str] = []
    notes = [
        "Baby-schema scores are bounded image heuristics/proxies, not biometric measurements.",
        "Generalized cute-character mode supports both human and non-human protagonists.",
    ]
    if not generalized_mode:
        notes.append("Generalized mode disabled; interpretation should be human-character focused.")
    if top_var < 5.0 and bottom_var < 5.0:
        warnings.append("Low visual contrast limits baby-schema proxy confidence.")
    if composite < 0.38:
        warnings.append("Cuteness proxy is weak; lead-character emotional pull may underperform.")

    confidence = _clamp01(0.25 + min(0.5, (top_var + bottom_var) / 110.0) + min(0.25, soft_patch.size / max(gray.size, 1)))

    return BabySchemaScoreResult(
        head_to_body_ratio_score=round(head_to_body_ratio_score, 4),
        eye_prominence_score=round(eye_prominence_score, 4),
        face_roundness_score=round(face_roundness_score, 4),
        cheek_fullness_or_softness_score=round(cheek_fullness_or_softness_score, 4),
        limb_shortness_softness_score=round(limb_shortness_softness_score, 4),
        overall_cuteness_proxy_score=round(overall, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
    )
