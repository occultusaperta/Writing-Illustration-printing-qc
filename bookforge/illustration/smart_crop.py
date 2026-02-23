from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image


def _edge_heatmap(gray: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(gray, dtype=np.float32)
    gy = np.zeros_like(gray, dtype=np.float32)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.sqrt(gx * gx + gy * gy)


def find_focus_centroid(image_path: Path) -> Tuple[float, float]:
    with Image.open(image_path) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    heat = _edge_heatmap(arr)
    h, w = heat.shape
    total = float(heat.sum())
    if total <= 1e-6:
        return (w * 0.5, h * 0.5)
    yy, xx = np.indices(heat.shape)
    cx = float((heat * xx).sum() / total)
    cy = float((heat * yy).sum() / total)
    return cx, cy


def smart_crop_to_target(im: Image.Image, target_w: int, target_h: int, safe_center_bias: tuple[float, float] = (0.5, 0.55)) -> Image.Image:
    work = im.convert("RGB")
    src_w, src_h = work.size
    if src_w == target_w and src_h == target_h:
        return work

    arr = np.asarray(work.convert("L"), dtype=np.float32)
    heat = _edge_heatmap(arr)
    total = float(heat.sum())
    if total <= 1e-6:
        focus_x, focus_y = src_w * 0.5, src_h * 0.5
    else:
        yy, xx = np.indices(heat.shape)
        focus_x = float((heat * xx).sum() / total)
        focus_y = float((heat * yy).sum() / total)

    bias_x = float(np.clip(safe_center_bias[0], 0.0, 1.0)) * src_w
    bias_y = float(np.clip(safe_center_bias[1], 0.0, 1.0)) * src_h
    center_x = 0.7 * focus_x + 0.3 * bias_x
    center_y = 0.7 * focus_y + 0.3 * bias_y

    left = int(round(center_x - target_w / 2))
    top = int(round(center_y - target_h / 2))
    left = max(0, min(left, src_w - target_w))
    top = max(0, min(top, src_h - target_h))
    return work.crop((left, top, left + target_w, top + target_h))
