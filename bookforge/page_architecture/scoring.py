from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np
from PIL import Image

from bookforge.page_architecture.types import ArchitectureVariant, ZoneType
from bookforge.scoring_registry import scoring_registry
from bookforge.qc.visual_integrity import face_like_regions


@dataclass(frozen=True)
class ArchitectureVariantScoreResult:
    variant_id: str
    architecture_type: str
    text_readability_score: float
    focal_alignment_score: float
    text_fitting_score: float
    gutter_safety_score: float
    composite_score: float
    diagnostics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _as_variant_dict(variant: ArchitectureVariant | Dict[str, Any]) -> Dict[str, Any]:
    if hasattr(variant, "__dataclass_fields__"):
        return {
            "variant_id": str(getattr(variant, "variant_id", "")),
            "architecture_type": getattr(variant, "architecture_type").value,
            "zones": [
                {
                    "zone_id": z.zone_id,
                    "zone_type": z.zone_type.value,
                    "x": z.x,
                    "y": z.y,
                    "w": z.w,
                    "h": z.h,
                }
                for z in getattr(variant, "zones", [])
            ],
        }
    return {
        "variant_id": str(variant.get("variant_id", "")),
        "architecture_type": str(variant.get("architecture_type", "full_bleed_single")),
        "zones": list(variant.get("zones", [])),
    }


def _gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _zones_by_type(zones: Sequence[Dict[str, Any]], accepted: Iterable[str]) -> List[Dict[str, Any]]:
    wanted = set(accepted)
    return [z for z in zones if str(z.get("zone_type", "")).lower() in wanted]


def _zone_slice(arr: np.ndarray, zone: Dict[str, Any]) -> np.ndarray:
    h, w = arr.shape[:2]
    x0 = int(np.clip(float(zone.get("x", 0.0)) * w, 0, w - 1))
    y0 = int(np.clip(float(zone.get("y", 0.0)) * h, 0, h - 1))
    x1 = int(np.clip((float(zone.get("x", 0.0)) + float(zone.get("w", 0.0))) * w, x0 + 1, w))
    y1 = int(np.clip((float(zone.get("y", 0.0)) + float(zone.get("h", 0.0))) * h, y0 + 1, h))
    return arr[y0:y1, x0:x1]


def _saliency_map(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
    sal = gx + gy
    maxv = float(np.max(sal))
    if maxv <= 1e-6:
        return np.zeros_like(sal)
    return np.clip(sal / maxv, 0.0, 1.0)


def score_text_readability(zones: Sequence[Dict[str, Any]], rgb: np.ndarray, architecture_type: str) -> tuple[float, Dict[str, Any]]:
    text_zones = _zones_by_type(zones, {ZoneType.TEXT.value, ZoneType.CAPTION.value})
    if not text_zones:
        return 1.0, {"reason": "no_text_zone_declared"}

    gray = _gray(rgb)
    sal = _saliency_map(gray)
    zone_scores: List[float] = []
    details = []
    for zone in text_zones:
        z_gray = _zone_slice(gray, zone)
        z_sal = _zone_slice(sal, zone)
        contrast_potential = float(np.clip(np.std(z_gray) / 64.0, 0.0, 1.0))
        busy = float(np.mean(z_sal))
        detail_penalty = float(np.clip(np.percentile(z_sal, 90), 0.0, 1.0))
        zone_score = _clip01(0.55 * (1.0 - busy) + 0.25 * (1.0 - detail_penalty) + 0.20 * contrast_potential)
        zone_scores.append(zone_score)
        details.append(
            {
                "zone_id": zone.get("zone_id", "text"),
                "background_busyness": round(busy, 4),
                "detail_penalty": round(detail_penalty, 4),
                "contrast_potential": round(contrast_potential, 4),
                "score": round(zone_score, 4),
            }
        )

    over_image_penalty = 0.08 if architecture_type in {"full_bleed_single", "full_bleed_spread", "wordless_spread"} else 0.0
    score = _clip01(float(np.mean(zone_scores)) - over_image_penalty)
    return score, {"zone_breakdown": details, "over_image_penalty": round(over_image_penalty, 4)}


def score_focal_alignment(zones: Sequence[Dict[str, Any]], rgb: np.ndarray) -> tuple[float, Dict[str, Any]]:
    gray = _gray(rgb)
    sal = _saliency_map(gray)
    focal_idx = int(np.argmax(sal))
    h, w = sal.shape
    fy, fx = divmod(focal_idx, w)
    fx_n, fy_n = fx / max(w - 1, 1), fy / max(h - 1, 1)

    art_zones = _zones_by_type(zones, {ZoneType.ART.value, ZoneType.INSET.value})
    text_zones = _zones_by_type(zones, {ZoneType.TEXT.value, ZoneType.CAPTION.value})

    def contains(zone: Dict[str, Any]) -> bool:
        x, y = float(zone.get("x", 0.0)), float(zone.get("y", 0.0))
        ww, hh = float(zone.get("w", 0.0)), float(zone.get("h", 0.0))
        return x <= fx_n <= x + ww and y <= fy_n <= y + hh

    in_art = any(contains(z) for z in art_zones)
    in_text = any(contains(z) for z in text_zones)
    focal_strength = float(np.max(sal))
    score = _clip01(0.7 * (1.0 if in_art else 0.25) + 0.2 * (0.0 if in_text else 1.0) + 0.1 * focal_strength)
    return score, {
        "focal_point": {"x": round(fx_n, 4), "y": round(fy_n, 4)},
        "focal_strength": round(focal_strength, 4),
        "in_art_zone": in_art,
        "in_text_zone": in_text,
    }


def estimate_text_fitting(page_text: str, zones: Sequence[Dict[str, Any]], age_range: str | None = None) -> tuple[float, Dict[str, Any]]:
    text_zones = _zones_by_type(zones, {ZoneType.TEXT.value, ZoneType.CAPTION.value})
    if not text_zones:
        return 1.0, {"reason": "no_text_zone_declared"}

    total_area = float(sum(float(z.get("w", 0.0)) * float(z.get("h", 0.0)) for z in text_zones))
    words = [w for w in page_text.strip().split() if w]
    word_count = len(words)
    char_count = sum(len(w) for w in words)
    age_factor = 0.85 if str(age_range or "").startswith("3") else 1.0
    capacity = max(1.0, total_area * 900.0 * age_factor)
    demand = max(word_count * 4.2, char_count * 0.55)
    fit_ratio = demand / capacity
    score = _clip01(1.0 - max(0.0, fit_ratio - 1.0))
    return score, {
        "word_count": word_count,
        "char_count": char_count,
        "text_zone_area": round(total_area, 4),
        "capacity_estimate": round(capacity, 2),
        "demand_estimate": round(demand, 2),
        "fit_ratio": round(fit_ratio, 4),
    }


def score_gutter_safety(zones: Sequence[Dict[str, Any]], rgb: np.ndarray, image_path: Path | None = None) -> tuple[float, Dict[str, Any]]:
    gray = _gray(rgb)
    sal = _saliency_map(gray)
    h, w = gray.shape
    seam_half_width = max(1, int(w * 0.06))
    cx = w // 2
    gutter_slice = sal[:, max(0, cx - seam_half_width) : min(w, cx + seam_half_width)]
    gutter_detail = float(np.mean(gutter_slice)) if gutter_slice.size else 0.0
    focal_in_gutter = bool(np.argmax(sal) % w in range(max(0, cx - seam_half_width), min(w, cx + seam_half_width)))

    text_overlap = 0.0
    for z in _zones_by_type(zones, {ZoneType.TEXT.value, ZoneType.CAPTION.value, ZoneType.ART.value, ZoneType.INSET.value}):
        x0 = float(z.get("x", 0.0))
        x1 = x0 + float(z.get("w", 0.0))
        seam0 = 0.5 - 0.06
        seam1 = 0.5 + 0.06
        overlap = max(0.0, min(x1, seam1) - max(x0, seam0))
        text_overlap = max(text_overlap, overlap / max(float(z.get("w", 1.0)), 1e-6))

    faces = face_like_regions(image_path) if image_path else 0
    face_penalty = 0.12 if faces > 0 else 0.0
    score = _clip01(1.0 - (0.55 * gutter_detail + 0.25 * text_overlap + (0.2 if focal_in_gutter else 0.0) + face_penalty))
    return score, {
        "gutter_detail_density": round(gutter_detail, 4),
        "focal_peak_in_gutter": focal_in_gutter,
        "seam_overlap_ratio": round(text_overlap, 4),
        "face_like_regions": int(faces),
    }


def score_architecture_variant(
    variant: ArchitectureVariant | Dict[str, Any],
    page_text: str,
    image: Path | str,
    page_color_spec: Dict[str, Any] | None = None,
    age_range: str | None = None,
) -> ArchitectureVariantScoreResult:
    _ = page_color_spec
    normalized = _as_variant_dict(variant)
    image_path = Path(image)
    with Image.open(image_path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)

    zones = normalized.get("zones", [])
    architecture_type = str(normalized.get("architecture_type", "full_bleed_single"))
    readability, read_diag = score_text_readability(zones, rgb, architecture_type)
    focal, focal_diag = score_focal_alignment(zones, rgb)
    fit, fit_diag = estimate_text_fitting(page_text=page_text, zones=zones, age_range=age_range)
    gutter, gutter_diag = score_gutter_safety(zones, rgb, image_path=image_path)

    weights = scoring_registry().page_architecture.composite_weights
    composite = _clip01(weights["readability"] * readability + weights["focal"] * focal + weights["fit"] * fit + weights["gutter"] * gutter)
    diagnostics = {
        "text_readability": read_diag,
        "focal_alignment": focal_diag,
        "text_fitting": fit_diag,
        "gutter_safety": gutter_diag,
        "notes": [
            "text_zone_conflict_detected" if readability < 0.45 else "text_zone_readability_ok",
            "gutter_risk_detected" if gutter < 0.5 else "gutter_risk_low",
        ],
    }
    return ArchitectureVariantScoreResult(
        variant_id=str(normalized.get("variant_id", "")),
        architecture_type=architecture_type,
        text_readability_score=round(readability, 4),
        focal_alignment_score=round(focal, 4),
        text_fitting_score=round(fit, 4),
        gutter_safety_score=round(gutter, 4),
        composite_score=round(composite, 4),
        diagnostics=diagnostics,
    )
