from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def _load_rgb(image_path: str | Path) -> np.ndarray:
    with Image.open(image_path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def _to_gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _connected_components(mask: np.ndarray) -> list[int]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    sizes: list[int] = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            q = deque([(y, x)])
            seen[y, x] = True
            size = 0
            while q:
                cy, cx = q.popleft()
                size += 1
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            sizes.append(size)
    return sizes


def text_likelihood(image_path: str | Path) -> float:
    arr = _load_rgb(image_path)
    gray = _to_gray(arr)
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    edges = gx + gy

    h, w = gray.shape
    strip_h = max(8, h // 6)
    strips = np.concatenate([edges[:strip_h, :], edges[-strip_h:, :]], axis=0)
    edge_density = float((strips > 28).mean())

    binary = strips > 38
    comps = _connected_components(binary)
    area = strips.shape[0] * strips.shape[1]
    min_size = max(6, area // 25000)
    max_size = max(min_size + 1, area // 300)
    glyph_like = [s for s in comps if min_size <= s <= max_size]
    concentration = min(1.0, len(glyph_like) / max(1.0, (w / 28.0)))
    score = 0.45 * min(1.0, edge_density * 6.0) + 0.55 * concentration
    return float(np.clip(score, 0.0, 1.0))


def watermark_likelihood(image_path: str | Path) -> float:
    arr = _load_rgb(image_path)
    gray = _to_gray(arr)
    h, w = gray.shape
    ch, cw = max(12, h // 5), max(12, w // 5)
    corners = [gray[:ch, :cw], gray[:ch, -cw:], gray[-ch:, :cw], gray[-ch:, -cw:]]
    vals = []
    for c in corners:
        d1 = np.abs(c[1:, 1:] - c[:-1, :-1]).mean()
        d2 = np.abs(c[1:, :-1] - c[:-1, 1:]).mean()
        diag_energy = (d1 + d2) / 2.0
        checker = c[::2, ::2].mean() - c[1::2, 1::2].mean() if c.shape[0] > 2 and c.shape[1] > 2 else 0.0
        vals.append(min(1.0, (diag_energy / 42.0)) * min(1.0, abs(checker) / 18.0 + 0.25))
    return float(np.clip(np.mean(vals), 0.0, 1.0))


def logo_likelihood(image_path: str | Path) -> float:
    arr = _load_rgb(image_path)
    gray = _to_gray(arr)
    h, w = gray.shape
    ch, cw = max(16, h // 4), max(16, w // 4)
    corners = [gray[:ch, :cw], gray[:ch, -cw:], gray[-ch:, :cw], gray[-ch:, -cw:]]
    scores = []
    for c in corners:
        mean = c.mean()
        mask = np.abs(c - mean) > 42
        comps = _connected_components(mask)
        if not comps:
            scores.append(0.0)
            continue
        blob = max(comps)
        area = c.shape[0] * c.shape[1]
        compact = 1.0 - min(1.0, abs((blob / area) - 0.05) / 0.05)
        p, _ = np.histogram(c, bins=32, range=(0, 255), density=True)
        p = p[p > 0]
        entropy = -np.sum(p * np.log2(p)) if p.size else 0.0
        low_entropy = 1.0 - min(1.0, entropy / 4.5)
        contrast = min(1.0, np.std(c) / 48.0)
        scores.append(np.clip(0.5 * compact + 0.3 * low_entropy + 0.2 * contrast, 0.0, 1.0))
    return float(np.max(scores) if scores else 0.0)


def border_artifact_score(image_path: str | Path) -> float:
    arr = _load_rgb(image_path)
    gray = _to_gray(arr)
    h, w = gray.shape
    b = max(3, int(min(h, w) * 0.06))
    strips = [gray[:b, :], gray[-b:, :], gray[:, :b], gray[:, -b:]]
    inner = [gray[b : 2 * b, :], gray[h - 2 * b : h - b, :], gray[:, b : 2 * b], gray[:, w - 2 * b : w - b]]
    scores = []
    for s, inn in zip(strips, inner):
        if s.size == 0 or inn.size == 0:
            scores.append(0.0)
            continue
        uniform = 1.0 - min(1.0, float(np.std(s)) / 10.0)
        cliff = min(1.0, abs(float(np.mean(s) - np.mean(inn))) / 35.0)
        line = min(1.0, (np.abs(np.diff(s, axis=0)).mean() + np.abs(np.diff(s, axis=1)).mean()) / 18.0)
        scores.append(np.clip(0.55 * uniform + 0.35 * cliff + 0.10 * (1.0 - line), 0.0, 1.0))
    return float(np.mean(scores))


def face_like_regions(image_path: str | Path) -> int:
    arr = _load_rgb(image_path)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    skin = (r > 70) & (g > 45) & (b > 35) & ((np.maximum.reduce([r, g, b]) - np.minimum.reduce([r, g, b])) > 10) & (r > g) & (r > b)
    comps = _connected_components(skin)
    h, w = skin.shape
    area = h * w
    min_a = max(40, area // 1800)
    max_a = max(min_a + 1, area // 18)
    count = sum(1 for s in comps if min_a <= s <= max_a)
    return int(count)
