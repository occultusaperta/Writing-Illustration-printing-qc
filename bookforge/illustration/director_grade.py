from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image


def _tone_curve(arr: np.ndarray, preset: str, strength: float) -> np.ndarray:
    s = float(np.clip(strength, 0.0, 1.0))
    x = arr / 255.0
    gamma = {
        "neutral": 1.0,
        "cinematic_soft": 0.95,
        "watercolor_warm": 0.9,
        "storybook_lux": 0.88,
    }.get(preset, 0.88)
    filmic = np.power(np.clip((x - 0.02) / 0.98, 0, 1), gamma)
    s_curve = filmic * filmic * (3 - 2 * filmic)
    shadows = np.clip(s_curve + 0.04, 0, 1)
    highlights = np.where(shadows > 0.9, 0.9 + (shadows - 0.9) * 0.6, shadows)
    out = x * (1.0 - s) + highlights * s
    return np.clip(out * 255.0, 0, 255)


def _paper_texture(shape: tuple[int, int], seed: int, scale: float) -> np.ndarray:
    h, w = shape
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 1.0, size=(h, w)).astype(np.float32)
    coarse = rng.normal(0.0, 1.0, size=(max(1, h // 4), max(1, w // 4))).astype(np.float32)
    coarse_img = Image.fromarray(((coarse - coarse.min()) / (np.ptp(coarse) + 1e-6) * 255).astype(np.uint8), mode="L")
    coarse_up = np.asarray(coarse_img.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32)
    coarse_up = (coarse_up - coarse_up.mean()) / (coarse_up.std() + 1e-6)
    tex = 0.7 * base + 0.3 * coarse_up
    tex = tex / (np.std(tex) + 1e-6)
    return tex * max(0.1, scale)


def apply_director_grade(image: Image.Image, *, base_seed: int, page_no: int, enabled: bool = True, tone_curve_preset: str = "storybook_lux", tone_curve_strength: float = 0.35, paper_texture_strength: float = 0.08, paper_texture_scale: float = 1.0, global_grade_strength: float = 0.30) -> Image.Image:
    if not enabled:
        return image.convert("RGB")
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    curved = _tone_curve(arr, tone_curve_preset, tone_curve_strength)

    if global_grade_strength > 0:
        lum = (0.299 * curved[:, :, 0] + 0.587 * curved[:, :, 1] + 0.114 * curved[:, :, 2]) / 255.0
        target = np.clip(0.52 + (lum - lum.mean()) * 0.92, 0.0, 1.0)
        gain = (target / np.clip(lum, 1e-5, 1.0))[:, :, None]
        curved = np.clip(curved * (1.0 - global_grade_strength + global_grade_strength * gain), 0, 255)

    if paper_texture_strength > 0:
        seed_payload = f"paper|{base_seed}|{page_no}".encode("utf-8")
        tex_seed = int(hashlib.sha256(seed_payload).hexdigest()[:8], 16)
        tex = _paper_texture((arr.shape[0], arr.shape[1]), tex_seed, paper_texture_scale)
        curved = np.clip(curved + tex[:, :, None] * (paper_texture_strength * 8.0), 0, 255)

    return Image.fromarray(curved.astype(np.uint8), mode="RGB")
