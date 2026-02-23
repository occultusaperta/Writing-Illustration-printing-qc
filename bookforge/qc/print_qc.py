from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
from PIL import Image

def _hist(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"))
    out = []
    for ch in range(3):
        hist, _ = np.histogram(arr[:, :, ch], bins=32, range=(0, 256), density=True)
        out.append(hist)
    vec = np.concatenate(out)
    denom = np.linalg.norm(vec)
    return vec / denom if denom else vec


def _style_hist_similarity(image: Path, style_ref: Path) -> float:
    a = _hist(image)
    b = _hist(style_ref)
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def analyze_print_qc(image: Path, style_ref: Path | None = None) -> Dict[str, Any]:
    with Image.open(image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    mx = np.max(rgb, axis=2)
    mn = np.min(rgb, axis=2)
    sat = np.where(mx <= 0, 0.0, (mx - mn) / np.clip(mx, 1e-5, 255.0))

    r = rgb[:, :, 0] / 255.0
    g = rgb[:, :, 1] / 255.0
    b = rgb[:, :, 2] / 255.0
    k = 1.0 - np.maximum.reduce([r, g, b])
    c = (1.0 - r - k) / np.clip(1.0 - k, 1e-5, 1.0)
    m = (1.0 - g - k) / np.clip(1.0 - k, 1e-5, 1.0)
    y = (1.0 - b - k) / np.clip(1.0 - k, 1e-5, 1.0)
    pegged = ((k > 0.92) | (c > 0.95) | (m > 0.95) | (y > 0.95)).mean()

    drift = 0.0
    if style_ref:
        drift = float(max(0.0, 1.0 - _style_hist_similarity(image, style_ref)))

    return {
        "brightness_mean": float(lum.mean()),
        "brightness_p05": float(np.percentile(lum, 5)),
        "brightness_p95": float(np.percentile(lum, 95)),
        "saturation_mean": float(sat.mean()),
        "color_drift_vs_style": drift,
        "out_of_gamut_risk": float(pegged),
    }


def print_qc_warnings(metrics: Dict[str, Any], qa_config: Dict[str, Any]) -> list[str]:
    warns: list[str] = []
    if metrics["brightness_p05"] < float(qa_config.get("min_brightness_p05", 15)):
        warns.append("brightness_p05_low")
    if metrics["brightness_p95"] > float(qa_config.get("max_brightness_p95", 245)):
        warns.append("brightness_p95_high")
    if metrics["out_of_gamut_risk"] > float(qa_config.get("max_out_of_gamut_risk", 0.35)):
        warns.append("out_of_gamut_risk_high")
    return warns
