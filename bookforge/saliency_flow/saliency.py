from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

from bookforge.saliency_flow.types import SaliencyFlowResult, SaliencyPeak


def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _gray(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def _box_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return arr
    out = np.zeros_like(arr)
    count = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out += np.roll(np.roll(arr, dy, axis=0), dx, axis=1)
            count += 1
    return out / max(count, 1)


def estimate_saliency_map(rgb: np.ndarray) -> np.ndarray:
    gray = _gray(rgb)
    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
    edges = gx + gy

    local_mean = _box_blur(gray, radius=2)
    local_contrast = np.abs(gray - local_mean)

    detail_density = _box_blur(edges, radius=1)

    h, w = gray.shape
    ys, xs = np.indices((h, w), dtype=np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    dist = np.sqrt(((xs - cx) / max(w, 1)) ** 2 + ((ys - cy) / max(h, 1)) ** 2)
    center_bias = np.clip(1.0 - dist * 1.6, 0.0, 1.0)

    raw = 0.46 * edges + 0.32 * local_contrast + 0.16 * detail_density + 0.06 * center_bias
    raw = np.maximum(raw, 0.0)
    mx = float(np.max(raw))
    if mx <= 1e-8:
        return np.zeros_like(raw)
    return np.clip(raw / mx, 0.0, 1.0)


def _zone_hint(x: float, y: float) -> str:
    if x > 0.67:
        return "right"
    if x < 0.33:
        return "left"
    if y < 0.33:
        return "upper"
    if y > 0.67:
        return "lower"
    return "center"


def extract_top_peaks(saliency: np.ndarray, top_k: int = 3, min_separation_px: int = 18) -> List[SaliencyPeak]:
    work = saliency.copy()
    h, w = work.shape
    peaks: List[SaliencyPeak] = []
    for rank in range(1, top_k + 1):
        idx = int(np.argmax(work))
        y, x = divmod(idx, w)
        strength = float(work[y, x])
        if strength <= 1e-6:
            break
        xn, yn = x / max(w - 1, 1), y / max(h - 1, 1)
        peaks.append(SaliencyPeak(rank=rank, x=round(xn, 4), y=round(yn, 4), strength=round(_clip01(strength), 4), zone_hint=_zone_hint(xn, yn)))

        y0 = max(0, y - min_separation_px)
        y1 = min(h, y + min_separation_px + 1)
        x0 = max(0, x - min_separation_px)
        x1 = min(w, x + min_separation_px + 1)
        work[y0:y1, x0:x1] = 0.0
    return peaks


def analyze_saliency_flow(image_path: Path | str) -> Tuple[np.ndarray, SaliencyFlowResult]:
    with Image.open(Path(image_path)) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)

    saliency = estimate_saliency_map(rgb)
    peaks = extract_top_peaks(saliency, top_k=3)
    h, w = saliency.shape
    ys, xs = np.indices((h, w), dtype=np.float32)
    total = float(saliency.sum()) + 1e-8
    com_x = float((saliency * xs).sum() / total) / max(w - 1, 1)
    com_y = float((saliency * ys).sum() / total) / max(h - 1, 1)

    half_x = w // 2
    half_y = h // 2
    left = float(saliency[:, :half_x].sum())
    right = float(saliency[:, half_x:].sum())
    upper = float(saliency[:half_y, :].sum())
    lower = float(saliency[half_y:, :].sum())

    directional = {
        "rightward_bias": round(_clip01((right - left) / total * 0.5 + 0.5), 4),
        "leftward_bias": round(_clip01((left - right) / total * 0.5 + 0.5), 4),
        "upward_bias": round(_clip01((upper - lower) / total * 0.5 + 0.5), 4),
        "downward_bias": round(_clip01((lower - upper) / total * 0.5 + 0.5), 4),
    }
    warnings = ["saliency_peaks_weak_or_flat"] if not peaks or peaks[0].strength < 0.28 else []
    notes = ["simulated saliency from local contrast/edge heuristics"]
    confidence = 0.72 if peaks else 0.35

    return saliency, SaliencyFlowResult(
        map_shape=[int(h), int(w)],
        peaks=peaks,
        first_fixation=peaks[0] if peaks else None,
        center_of_mass={"x": round(_clip01(com_x), 4), "y": round(_clip01(com_y), 4)},
        directional_energy=directional,
        confidence=confidence,
        warnings=warnings,
        notes=notes,
    )
