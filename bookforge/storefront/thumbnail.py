from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.storefront.types import CoverThumbnailDiagnostics, ThumbnailScoreResult


def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _edge_density(gray: np.ndarray) -> float:
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge_ratio_x = float(np.mean(gx > 22.0)) if gx.size else 0.0
    edge_ratio_y = float(np.mean(gy > 22.0)) if gy.size else 0.0
    return float((edge_ratio_x + edge_ratio_y) * 0.5)


def _focus_strength(gray: np.ndarray) -> float:
    h, w = gray.shape
    cy0, cy1 = int(h * 0.25), int(h * 0.75)
    cx0, cx1 = int(w * 0.25), int(w * 0.75)
    center = gray[cy0:cy1, cx0:cx1]
    border_mask = np.ones_like(gray, dtype=bool)
    border_mask[cy0:cy1, cx0:cx1] = False
    border = gray[border_mask]
    if center.size == 0 or border.size == 0:
        return 0.5
    cstd = float(np.std(center))
    bstd = float(np.std(border))
    return _clip01(0.5 + (cstd - bstd) / 80.0)


def _title_band_readability(gray: np.ndarray) -> float:
    h, w = gray.shape
    band_h = max(8, int(h * 0.26))
    top = gray[:band_h, :]
    if top.size == 0:
        return 0.35
    band_contrast = float(np.std(top))
    local = np.abs(np.diff(top, axis=1))
    stroke_signal = float(np.percentile(local, 75)) if local.size else 0.0
    return _clip01(0.2 + (band_contrast / 80.0) + (stroke_signal / 140.0))


def _character_visibility(rgb: np.ndarray) -> float:
    sat = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    bright = np.mean(rgb, axis=2)
    salient = (sat > 35) & (bright > 45) & (bright < 225)
    ratio = float(np.mean(salient)) if salient.size else 0.0
    if ratio < 0.02:
        return 0.25
    if ratio > 0.45:
        return 0.65
    return _clip01(0.35 + ratio * 1.4)


def _emotional_tone_clarity(rgb: np.ndarray) -> float:
    sat = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    mean_sat = float(np.mean(sat))
    luma = _gray(rgb)
    luma_std = float(np.std(luma))
    return _clip01(0.25 + (mean_sat / 130.0) + (luma_std / 110.0))


def score_cover_thumbnail(path: Path, *, thumbnail_heights: List[int] | None = None, title_text_available: bool = False) -> CoverThumbnailDiagnostics:
    heights = thumbnail_heights or [100, 128, 160]
    per_size: List[Dict[str, Any]] = []
    warnings: List[str] = []
    notes: List[str] = []

    with Image.open(path) as im:
        rgb_src = im.convert("RGB")
        for h in heights:
            aspect = rgb_src.width / max(rgb_src.height, 1)
            w = max(40, int(h * aspect))
            thumb = rgb_src.resize((w, h), Image.Resampling.LANCZOS)
            arr = np.asarray(thumb, dtype=np.float32)
            gray = _gray(arr)

            title_score = _title_band_readability(gray)
            focal_score = _focus_strength(gray)
            char_score = _character_visibility(arr)
            contrast_score = _clip01(float(np.std(gray)) / 72.0)
            tone_score = _emotional_tone_clarity(arr)
            clutter_penalty = _clip01(max(0.0, (_edge_density(gray) - 0.18) / 0.55))
            clutter_score = _clip01(1.0 - clutter_penalty)

            comp = _clip01(
                0.26 * title_score
                + 0.19 * focal_score
                + 0.15 * char_score
                + 0.18 * contrast_score
                + 0.12 * tone_score
                + 0.10 * clutter_score
            )
            per_size.append(
                {
                    "thumbnail_height": int(h),
                    "title_readability_score": round(title_score, 4),
                    "focal_clarity_score": round(focal_score, 4),
                    "character_visibility_score": round(char_score, 4),
                    "contrast_at_thumbnail_score": round(contrast_score, 4),
                    "emotional_tone_clarity_score": round(tone_score, 4),
                    "clutter_penalty": round(clutter_penalty, 4),
                    "clutter_score": round(clutter_score, 4),
                    "composite_score": round(comp, 4),
                }
            )

    if not title_text_available:
        warnings.append("title_layer_unavailable_readability_is_proxy_only")
        notes.append("Title readability uses top-band contrast/edge heuristics; OCR/text-layer validation is not active.")

    avg = lambda key: float(np.mean([float(s.get(key, 0.0) or 0.0) for s in per_size])) if per_size else 0.0

    aggregate = ThumbnailScoreResult(
        title_readability_score=round(avg("title_readability_score"), 4),
        focal_clarity_score=round(avg("focal_clarity_score"), 4),
        character_visibility_score=round(avg("character_visibility_score"), 4),
        contrast_at_thumbnail_score=round(avg("contrast_at_thumbnail_score"), 4),
        emotional_tone_clarity_score=round(avg("emotional_tone_clarity_score"), 4),
        clutter_penalty=round(avg("clutter_penalty"), 4),
        clutter_score=round(avg("clutter_score"), 4),
        composite_score=round(avg("composite_score"), 4),
        confidence=round(_clip01(0.52 + (0.18 if title_text_available else 0.0) + min(0.2, 0.05 * len(per_size))), 4),
        warnings=warnings,
        notes=notes,
    )

    if aggregate.title_readability_score < 0.42:
        aggregate.warnings.append("thumbnail_title_readability_weak")
    if aggregate.focal_clarity_score < 0.45:
        aggregate.warnings.append("thumbnail_focal_clarity_weak")
    if aggregate.clutter_penalty > 0.58:
        aggregate.warnings.append("thumbnail_clutter_risk_high")

    return CoverThumbnailDiagnostics(
        cover_path=str(path),
        thumbnail_heights=[int(h) for h in heights],
        per_size_scores=per_size,
        aggregate=aggregate,
    )
