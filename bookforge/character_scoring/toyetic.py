from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from bookforge.character_scoring.types import SilhouetteScoreResult, ToyeticScoreResult
from bookforge.utils import clamp01


def _load_rgb(path: str | Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def score_toyetic(image_path: str | Path, silhouette: SilhouetteScoreResult) -> ToyeticScoreResult:
    arr = _load_rgb(image_path)
    h, w, _ = arr.shape

    flat = arr.reshape(-1, 3)
    quantized = (flat // 32).astype(int)
    unique_bins = np.unique(quantized[:, 0] * 64 + quantized[:, 1] * 8 + quantized[:, 2])
    color_bins = float(len(unique_bins))

    color_reproducibility = clamp01(1.0 - abs(color_bins - 14.0) / 20.0)
    signature_feature = clamp01(0.5 * silhouette.distinguishability_score + 0.3 * silhouette.iconic_readability_score + 0.2 * (1.0 - abs(color_bins - 10.0) / 18.0))

    left = arr[:, : w // 2, :]
    right = arr[:, w - (w // 2):, :][:, ::-1, :]
    symmetry = 1.0 - float(np.mean(np.abs(left - right)) / 255.0)
    angle_consistency = clamp01(0.25 + 0.75 * symmetry)

    complexity_penalty = 1.0 - silhouette.edge_complexity_score
    plush_friendliness = clamp01(0.6 * silhouette.compactness_score + 0.4 * (1.0 - complexity_penalty))

    thumb = np.asarray(Image.fromarray(arr.astype(np.uint8)).resize((48, 48), Image.Resampling.BILINEAR), dtype=np.float32)
    thumb_gray = 0.299 * thumb[:, :, 0] + 0.587 * thumb[:, :, 1] + 0.114 * thumb[:, :, 2]
    local_contrast = float(np.std(thumb_gray))
    small_scale = clamp01(0.5 * silhouette.iconic_readability_score + 0.5 * (local_contrast / 72.0))

    silhouette_distinctiveness = silhouette.distinguishability_score

    composite = clamp01(
        0.23 * silhouette_distinctiveness
        + 0.2 * signature_feature
        + 0.13 * color_reproducibility
        + 0.12 * angle_consistency
        + 0.17 * plush_friendliness
        + 0.15 * small_scale
    )

    warnings: list[str] = []
    notes: list[str] = ["Toyetic scoring is proxy-based and does not guarantee manufacturing success."]
    if plush_friendliness < 0.4:
        warnings.append("Shape/detail profile may be brittle for plush adaptation.")
    if silhouette_distinctiveness < 0.4:
        warnings.append("Silhouette distinctiveness is weak for series branding.")
    if signature_feature < 0.4:
        warnings.append("Signature feature strength is weak; character may feel generic.")

    confidence = clamp01(0.2 + 0.45 * silhouette.confidence + 0.35 * (local_contrast / 64.0))

    return ToyeticScoreResult(
        silhouette_distinctiveness_score=round(silhouette_distinctiveness, 4),
        signature_feature_score=round(signature_feature, 4),
        color_reproducibility_score=round(color_reproducibility, 4),
        angle_consistency_score=round(angle_consistency, 4),
        plush_friendliness_score=round(plush_friendliness, 4),
        small_scale_recognizability_score=round(small_scale, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
    )
