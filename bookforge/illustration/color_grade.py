from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List

import numpy as np
from PIL import Image, ImageFilter


def _hex_to_rgb(color: str) -> np.ndarray:
    raw = color.strip().lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"Invalid palette color: {color}")
    return np.array([int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)], dtype=np.float32)


def reinhard_color_transfer(src: Image.Image, ref: Image.Image, strength: float = 0.35) -> Image.Image:
    strength = float(np.clip(strength, 0.0, 1.0))
    src_arr = np.asarray(src.convert("RGB"), dtype=np.float32)
    ref_arr = np.asarray(ref.convert("RGB"), dtype=np.float32)

    src_mean = src_arr.reshape(-1, 3).mean(axis=0)
    src_std = src_arr.reshape(-1, 3).std(axis=0) + 1e-6
    ref_mean = ref_arr.reshape(-1, 3).mean(axis=0)
    ref_std = ref_arr.reshape(-1, 3).std(axis=0) + 1e-6

    normalized = (src_arr - src_mean) / src_std
    transferred = normalized * ref_std + ref_mean
    mixed = src_arr * (1.0 - strength) + transferred * strength
    mixed = np.clip(mixed, 0, 255).astype(np.uint8)
    return Image.fromarray(mixed, mode="RGB")


def palette_snap(src: Image.Image, palette_hex_list: Iterable[str], strength: float = 0.2) -> Image.Image:
    strength = float(np.clip(strength, 0.0, 1.0))
    colors: List[np.ndarray] = [_hex_to_rgb(c) for c in palette_hex_list if str(c).strip()]
    if not colors or strength <= 0:
        return src.convert("RGB")

    palette = np.stack(colors, axis=0)
    arr = np.asarray(src.convert("RGB"), dtype=np.float32)
    flat = arr.reshape(-1, 3)
    distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    nearest = palette[np.argmin(distances, axis=1)]
    blended = flat * (1.0 - strength) + nearest * strength
    out = np.clip(blended, 0, 255).reshape(arr.shape).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def add_sharpen_and_grain(image: Image.Image, sharpen_amount: float = 0.15, grain_amount: float = 0.05, grain_seed: int | None = None) -> Image.Image:
    sharpen_amount = float(np.clip(sharpen_amount, 0.0, 1.0))
    grain_amount = float(np.clip(grain_amount, 0.0, 1.0))
    rgb = image.convert("RGB")
    if sharpen_amount > 0:
        sharp = rgb.filter(ImageFilter.UnsharpMask(radius=1.0, percent=int(70 + sharpen_amount * 80), threshold=2))
        arr = np.asarray(rgb, dtype=np.float32)
        sarr = np.asarray(sharp, dtype=np.float32)
        rgb = Image.fromarray(np.clip(arr * (1.0 - sharpen_amount) + sarr * sharpen_amount, 0, 255).astype(np.uint8), mode="RGB")

    if grain_amount > 0:
        arr = np.asarray(rgb, dtype=np.float32)
        h, w, _ = arr.shape
        if grain_seed is None:
            seed_input = arr.tobytes() + f"|{grain_amount:.4f}".encode("utf-8")
            seed = int(hashlib.sha256(seed_input).hexdigest()[:8], 16)
        else:
            seed = int(grain_seed)
        rng = np.random.default_rng(seed)
        noise = rng.normal(loc=0.0, scale=grain_amount * 18.0, size=(h, w, 1)).astype(np.float32)
        out = np.clip(arr + noise, 0, 255).astype(np.uint8)
        rgb = Image.fromarray(out, mode="RGB")
    return rgb


def grade_image(src_path: Path, style_ref_path: Path, palette: list[str], mode: str = "match_style", strength: float = 0.35) -> Image.Image:
    with Image.open(src_path) as src_im, Image.open(style_ref_path) as style_im:
        base = src_im.convert("RGB")
        if mode == "off":
            return base
        graded = reinhard_color_transfer(base, style_im.convert("RGB"), strength=strength)
        if mode == "match_style_plus_palette":
            graded = palette_snap(graded, palette, strength=min(0.3, strength))
        return graded
