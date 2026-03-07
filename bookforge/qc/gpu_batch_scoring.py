from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
from PIL import Image

try:
    import torch
    import torch.nn.functional as F
except Exception:  # pragma: no cover - torch is optional
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


def gpu_batch_scoring_enabled() -> bool:
    return (os.getenv("BOOKFORGE_GPU_BATCH_SCORING") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _load_batch(paths: Iterable[Path]) -> np.ndarray:
    arrs: List[np.ndarray] = []
    for p in paths:
        with Image.open(p) as im:
            arrs.append(np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0)
    if not arrs:
        return np.zeros((0, 1, 1, 3), dtype=np.float32)
    h = min(a.shape[0] for a in arrs)
    w = min(a.shape[1] for a in arrs)
    clipped = [a[:h, :w, :] for a in arrs]
    return np.stack(clipped, axis=0)


def _to_luma_torch(batch: "torch.Tensor") -> "torch.Tensor":
    return 0.299 * batch[:, 0] + 0.587 * batch[:, 1] + 0.114 * batch[:, 2]


def _score_torch_cuda(batch_np: np.ndarray) -> Dict[str, np.ndarray]:
    assert torch is not None and F is not None
    device = torch.device("cuda")
    batch = torch.from_numpy(np.transpose(batch_np, (0, 3, 1, 2))).to(device=device, dtype=torch.float32)
    gray = _to_luma_torch(batch)

    # Texture/detail proxy via gradient magnitude.
    gx = gray[:, :, 1:] - gray[:, :, :-1]
    gy = gray[:, 1:, :] - gray[:, :-1, :]
    grad_mag = torch.mean(torch.abs(gx[:, :-1, :]) + torch.abs(gy[:, :, :-1]), dim=(1, 2))

    # Laplacian variance proxy for sharpness.
    kernel = torch.tensor([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]], device=device).view(1, 1, 3, 3)
    lap = F.conv2d(gray.unsqueeze(1), kernel, padding=1).squeeze(1)
    sharpness = torch.var(lap.reshape(lap.shape[0], -1), dim=1)

    # Focal/saliency proxy: center-weighted edge response.
    h, w = gray.shape[1], gray.shape[2]
    yy = torch.linspace(-1, 1, h, device=device).view(1, h, 1)
    xx = torch.linspace(-1, 1, w, device=device).view(1, 1, w)
    center_weight = torch.exp(-3.0 * (xx**2 + yy**2))
    saliency = torch.mean(torch.abs(lap) * center_weight, dim=(1, 2))

    # Composition anchor: upper-left golden area edge energy.
    y0, y1 = int(0.15 * h), int(0.55 * h)
    x0, x1 = int(0.10 * w), int(0.50 * w)
    anchor = torch.mean(torch.abs(lap[:, y0:y1, x0:x1]), dim=(1, 2)) if y1 > y0 and x1 > x0 else saliency

    # Normalize to stable 0-1 ranges for ranking use.
    def _norm(x: "torch.Tensor") -> np.ndarray:
        x = torch.clamp(x, min=0)
        m = torch.max(x)
        return (x / (m + 1e-6)).detach().cpu().numpy()

    return {
        "sharpness": _norm(sharpness),
        "texture_density": _norm(grad_mag),
        "detail_density": _norm(grad_mag * 0.7 + sharpness * 0.3),
        "saliency_score": _norm(saliency),
        "composition_score": _norm(anchor),
    }


def _score_cpu_numpy(batch_np: np.ndarray) -> Dict[str, np.ndarray]:
    if batch_np.shape[0] == 0:
        return {k: np.zeros((0,), dtype=np.float32) for k in ["sharpness", "texture_density", "detail_density", "saliency_score", "composition_score"]}
    gray = 0.299 * batch_np[:, :, :, 0] + 0.587 * batch_np[:, :, :, 1] + 0.114 * batch_np[:, :, :, 2]
    gx = gray[:, :, 1:] - gray[:, :, :-1]
    gy = gray[:, 1:, :] - gray[:, :-1, :]
    grad = np.mean(np.abs(gx[:, :-1, :]) + np.abs(gy[:, :, :-1]), axis=(1, 2))
    pad = np.pad(gray, ((0, 0), (1, 1), (1, 1)), mode="edge")
    lap = -4 * pad[:, 1:-1, 1:-1] + pad[:, :-2, 1:-1] + pad[:, 2:, 1:-1] + pad[:, 1:-1, :-2] + pad[:, 1:-1, 2:]
    sharp = np.var(lap.reshape(lap.shape[0], -1), axis=1)

    h, w = gray.shape[1], gray.shape[2]
    yy = np.linspace(-1, 1, h).reshape(1, h, 1)
    xx = np.linspace(-1, 1, w).reshape(1, 1, w)
    center_weight = np.exp(-3.0 * (xx**2 + yy**2))
    saliency = np.mean(np.abs(lap) * center_weight, axis=(1, 2))
    y0, y1 = int(0.15 * h), int(0.55 * h)
    x0, x1 = int(0.10 * w), int(0.50 * w)
    anchor = np.mean(np.abs(lap[:, y0:y1, x0:x1]), axis=(1, 2)) if y1 > y0 and x1 > x0 else saliency

    def _norm(x: np.ndarray) -> np.ndarray:
        x = np.clip(x, 0, None)
        m = float(np.max(x)) if x.size else 0.0
        return x / (m + 1e-6)

    return {
        "sharpness": _norm(sharp),
        "texture_density": _norm(grad),
        "detail_density": _norm(0.7 * grad + 0.3 * sharp),
        "saliency_score": _norm(saliency),
        "composition_score": _norm(anchor),
    }


def score_candidate_batch(paths: List[Path]) -> Dict[str, Dict[str, float]]:
    batch = _load_batch(paths)
    use_cuda = bool(torch is not None and torch.cuda.is_available())
    score_map = _score_torch_cuda(batch) if use_cuda else _score_cpu_numpy(batch)

    out: Dict[str, Dict[str, float]] = {}
    for idx, path in enumerate(paths):
        out[str(path)] = {
            "sharpness": float(score_map["sharpness"][idx]),
            "texture_density": float(score_map["texture_density"][idx]),
            "detail_density": float(score_map["detail_density"][idx]),
            "saliency_score": float(score_map["saliency_score"][idx]),
            "composition_score": float(score_map["composition_score"][idx]),
            "ranking_score": float(
                0.25 * score_map["composition_score"][idx]
                + 0.25 * score_map["saliency_score"][idx]
                + 0.25 * score_map["texture_density"][idx]
                + 0.25 * score_map["detail_density"][idx]
            ),
            "cuda_used": bool(use_cuda),
        }
    return out
