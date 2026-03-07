from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageFilter

try:
    import torch
    import torch.nn.functional as F
except Exception:  # pragma: no cover - torch is optional
    torch = None
    F = None


@dataclass(frozen=True)
class VisualEnsembleResult:
    composition_score: float
    clarity_score: float
    texture_score: float
    artifact_score: float
    perceptual_quality: float
    ensemble_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


_WEIGHTS = {
    "composition_score": 0.25,
    "clarity_score": 0.20,
    "texture_score": 0.15,
    "artifact_score": 0.20,
    "perceptual_quality": 0.20,
}


def _clamp01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _load_rgb(image: Image.Image | np.ndarray | Path | str) -> np.ndarray:
    if isinstance(image, np.ndarray):
        arr = image
    elif isinstance(image, Image.Image):
        arr = np.asarray(image.convert("RGB"))
    else:
        with Image.open(image) as im:
            arr = np.asarray(im.convert("RGB"))
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    return arr.astype(np.float32)


def _gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _gradient_map(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return gx + gy


def _composition_score(gray: np.ndarray) -> float:
    saliency = _gradient_map(gray)
    total = float(saliency.sum()) + 1e-8
    h, w = gray.shape

    ys = np.arange(h, dtype=np.float32)[:, None]
    xs = np.arange(w, dtype=np.float32)[None, :]
    cy = float((saliency * ys).sum() / total)
    cx = float((saliency * xs).sum() / total)

    thirds_x = np.array([w / 3.0, 2.0 * w / 3.0], dtype=np.float32)
    thirds_y = np.array([h / 3.0, 2.0 * h / 3.0], dtype=np.float32)
    tx = float(np.min(np.abs(thirds_x - cx)))
    ty = float(np.min(np.abs(thirds_y - cy)))
    thirds_dist = np.hypot(tx / max(w, 1), ty / max(h, 1))
    thirds_score = _clamp01(1.0 - thirds_dist * 2.2)

    center_dist = np.hypot((cx - (w * 0.5)) / max(w, 1), (cy - (h * 0.5)) / max(h, 1))
    focal_score = _clamp01(1.0 - center_dist * 1.8)

    thirds_grid_x = np.array_split(np.arange(w), 3)
    thirds_grid_y = np.array_split(np.arange(h), 3)
    cell_energy = [
        float(saliency[np.ix_(gy, gx)].mean())
        for gy in thirds_grid_y
        for gx in thirds_grid_x
        if len(gy) and len(gx)
    ]
    mean_energy = float(np.mean(cell_energy)) + 1e-8
    balance_cv = float(np.std(cell_energy) / mean_energy)
    balance_score = _clamp01(1.0 - balance_cv / 1.5)

    return _clamp01(0.45 * thirds_score + 0.25 * focal_score + 0.30 * balance_score)


def _clarity_score(gray: np.ndarray) -> float:
    lap = -4.0 * gray + np.roll(gray, 1, 0) + np.roll(gray, -1, 0) + np.roll(gray, 1, 1) + np.roll(gray, -1, 1)
    var = float(np.var(lap[1:-1, 1:-1]))
    return _clamp01(var / (var + 220.0))


def _texture_score(gray: np.ndarray) -> float:
    centered = gray - float(gray.mean())
    spec = np.fft.fftshift(np.fft.fft2(centered))
    energy = np.abs(spec) ** 2
    h, w = gray.shape
    yy, xx = np.mgrid[:h, :w]
    rr = np.sqrt((yy - h / 2.0) ** 2 + (xx - w / 2.0) ** 2)
    high = rr > (0.25 * min(h, w))
    ratio = float(energy[high].sum() / (energy.sum() + 1e-8))
    return _clamp01((ratio - 0.05) / 0.50)


def _artifact_score(gray: np.ndarray) -> float:
    # banding heuristic: too-few gradient bins in smooth regions
    grad = _gradient_map(gray)
    smooth_mask = grad < np.percentile(grad, 40)
    smooth_vals = gray[smooth_mask]
    if smooth_vals.size:
        bins = np.histogram(smooth_vals, bins=32, range=(0, 255))[0]
        banding_level = 1.0 - (np.count_nonzero(bins) / 32.0)
    else:
        banding_level = 0.0

    # noise spikes: unusually sharp local differences
    local_dev = np.abs(gray - np.median(gray))
    noise_level = float(np.percentile(local_dev, 99) / 80.0)

    # compression artifacts: 8px grid discontinuity
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    bx_idx = np.arange(7, gray.shape[1] - 1, 8)
    by_idx = np.arange(7, gray.shape[0] - 1, 8)
    block_x = float(gx[:, bx_idx].mean()) if len(bx_idx) else 0.0
    non_block_x = float(np.delete(gx, bx_idx, axis=1).mean()) if gx.shape[1] > len(bx_idx) else 0.0
    block_y = float(gy[by_idx, :].mean()) if len(by_idx) else 0.0
    non_block_y = float(np.delete(gy, by_idx, axis=0).mean()) if gy.shape[0] > len(by_idx) else 0.0
    blockiness = max(0.0, (block_x - non_block_x) / (non_block_x + 1e-6)) + max(0.0, (block_y - non_block_y) / (non_block_y + 1e-6))

    artifact_level = _clamp01(0.35 * banding_level + 0.25 * _clamp01(noise_level) + 0.40 * _clamp01(blockiness / 2.0))
    return _clamp01(1.0 - artifact_level)


def _ssim(gray_a: np.ndarray, gray_b: np.ndarray) -> float:
    a = gray_a.astype(np.float64)
    b = gray_b.astype(np.float64)
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a = float(a.mean())
    mu_b = float(b.mean())
    var_a = float(a.var())
    var_b = float(b.var())
    cov = float(((a - mu_a) * (b - mu_b)).mean())
    num = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
    den = (mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2)
    return _clamp01(num / (den + 1e-8))


def _perceptual_quality(rgb: np.ndarray, gray: np.ndarray) -> float:
    blur = np.asarray(Image.fromarray(rgb.astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=1.2)).convert("L"), dtype=np.float32)
    return _ssim(gray, blur)


def _ensemble_from_scores(scores: dict[str, float]) -> float:
    return _clamp01(sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS))


def evaluate_visual_ensemble(image: Image.Image | np.ndarray | Path | str) -> VisualEnsembleResult:
    rgb = _load_rgb(image)
    gray = _gray(rgb)
    composition_score = _composition_score(gray)
    clarity_score = _clarity_score(gray)
    texture_score = _texture_score(gray)
    artifact_score = _artifact_score(gray)
    perceptual_quality = _perceptual_quality(rgb, gray)
    score_map = {
        "composition_score": composition_score,
        "clarity_score": clarity_score,
        "texture_score": texture_score,
        "artifact_score": artifact_score,
        "perceptual_quality": perceptual_quality,
    }
    return VisualEnsembleResult(
        composition_score=composition_score,
        clarity_score=clarity_score,
        texture_score=texture_score,
        artifact_score=artifact_score,
        perceptual_quality=perceptual_quality,
        ensemble_score=_ensemble_from_scores(score_map),
    )


def evaluate_visual_ensemble_batch(images: Sequence[Image.Image | np.ndarray | Path | str]) -> list[VisualEnsembleResult]:
    if not images:
        return []
    if torch is None or not torch.cuda.is_available() or F is None:
        return [evaluate_visual_ensemble(image) for image in images]

    arrays = [_load_rgb(img) for img in images]
    h = min(arr.shape[0] for arr in arrays)
    w = min(arr.shape[1] for arr in arrays)
    trimmed = [arr[:h, :w, :] for arr in arrays]

    ten = torch.from_numpy(np.stack(trimmed)).to(device="cuda", dtype=torch.float32)
    gray = 0.299 * ten[:, :, :, 0] + 0.587 * ten[:, :, :, 1] + 0.114 * ten[:, :, :, 2]

    lap_kernel = torch.tensor([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]], device="cuda", dtype=torch.float32).view(1, 1, 3, 3)
    lap = F.conv2d(gray.unsqueeze(1), lap_kernel, padding=1).squeeze(1)
    clarity = (lap[:, 1:-1, 1:-1].var(dim=(1, 2)) / (lap[:, 1:-1, 1:-1].var(dim=(1, 2)) + 220.0)).clamp(0.0, 1.0)

    gx = torch.abs(gray - torch.roll(gray, shifts=1, dims=2))
    gy = torch.abs(gray - torch.roll(gray, shifts=1, dims=1))
    saliency = gx + gy

    ys = torch.arange(h, device="cuda", dtype=torch.float32).view(1, h, 1)
    xs = torch.arange(w, device="cuda", dtype=torch.float32).view(1, 1, w)
    total = saliency.sum(dim=(1, 2)) + 1e-8
    cy = (saliency * ys).sum(dim=(1, 2)) / total
    cx = (saliency * xs).sum(dim=(1, 2)) / total
    tx = torch.minimum(torch.abs(cx - (w / 3.0)), torch.abs(cx - (2.0 * w / 3.0)))
    ty = torch.minimum(torch.abs(cy - (h / 3.0)), torch.abs(cy - (2.0 * h / 3.0)))
    thirds_dist = torch.sqrt((tx / max(w, 1)) ** 2 + (ty / max(h, 1)) ** 2)
    composition = (1.0 - thirds_dist * 2.2).clamp(0.0, 1.0)

    fft_energy = torch.abs(torch.fft.fftshift(torch.fft.fft2(gray - gray.mean(dim=(1, 2), keepdim=True)), dim=(-2, -1))) ** 2
    yy, xx = torch.meshgrid(torch.arange(h, device="cuda", dtype=torch.float32), torch.arange(w, device="cuda", dtype=torch.float32), indexing="ij")
    rr = torch.sqrt((yy - h / 2.0) ** 2 + (xx - w / 2.0) ** 2)
    high = rr > (0.25 * min(h, w))
    texture = ((fft_energy[:, high].sum(dim=1) / (fft_energy.sum(dim=(1, 2)) + 1e-8) - 0.05) / 0.5).clamp(0.0, 1.0)

    results: list[VisualEnsembleResult] = []
    for idx, src in enumerate(images):
        cpu_res = evaluate_visual_ensemble(src)
        score_map = {
            "composition_score": float(composition[idx].item()),
            "clarity_score": float(clarity[idx].item()),
            "texture_score": float(texture[idx].item()),
            "artifact_score": cpu_res.artifact_score,
            "perceptual_quality": cpu_res.perceptual_quality,
        }
        results.append(
            VisualEnsembleResult(
                composition_score=score_map["composition_score"],
                clarity_score=score_map["clarity_score"],
                texture_score=score_map["texture_score"],
                artifact_score=score_map["artifact_score"],
                perceptual_quality=score_map["perceptual_quality"],
                ensemble_score=_ensemble_from_scores(score_map),
            )
        )
    return results
