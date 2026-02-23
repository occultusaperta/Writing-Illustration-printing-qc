from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
from PIL import Image


def _sobel(gray: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.sqrt(gx * gx + gy * gy)


def focus_bleed_overlap(path: Path, bleed_ratio: float = 0.1) -> Dict[str, float]:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = arr.shape
    sob = _sobel(arr)
    thresh = float(np.percentile(sob, 75))
    mask = sob >= max(1.0, thresh)
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return {"overlap": 0.0, "focus_box": [0, 0, w, h]}

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bleed_x = int(w * bleed_ratio)
    bleed_y = int(h * bleed_ratio)
    safe_x0, safe_y0 = bleed_x, bleed_y
    safe_x1, safe_y1 = w - bleed_x, h - bleed_y

    focus_area = float(max(1, (x1 - x0) * (y1 - y0)))
    out_left = max(0, safe_x0 - x0)
    out_right = max(0, x1 - safe_x1)
    out_top = max(0, safe_y0 - y0)
    out_bottom = max(0, y1 - safe_y1)
    overlap_area = float((out_left + out_right) * max(0, y1 - y0) + (out_top + out_bottom) * max(0, x1 - x0))
    overlap = min(1.0, overlap_area / focus_area)
    return {"overlap": overlap, "focus_box": [x0, y0, x1, y1]}
