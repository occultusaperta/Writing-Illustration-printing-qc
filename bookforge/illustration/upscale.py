from __future__ import annotations

import os
from pathlib import Path

from PIL import Image


def _target_resolution() -> int:
    target = int(os.getenv("BOOKFORGE_UPSCALE_TARGET", "4096"))
    return max(4096, target)


def _is_cover_or_spread(path: Path) -> bool:
    n = path.name.lower()
    return "cover" in n or "spread" in n


def upscale_image(path: Path) -> Path:
    mode = str(os.getenv("BOOKFORGE_UPSCALE_MODE", "tiled_diffusion")).strip().lower()
    esrgan_model = os.getenv("BOOKFORGE_ESRGAN_MODEL_PATH", "")
    tiled_model = os.getenv("BOOKFORGE_TILED_UPSCALE_MODEL_PATH", "")
    if mode == "esrgan" and not esrgan_model:
        mode = "bicubic"
    if mode == "tiled_diffusion" and not tiled_model:
        mode = "esrgan" if esrgan_model else "bicubic"

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        target = 8192 if _is_cover_or_spread(path) and str(os.getenv("BOOKFORGE_UPSCALE_8192", "false")).lower() in {"1", "true", "yes", "on"} else _target_resolution()
        scale = max(target / max(rgb.width, 1), target / max(rgb.height, 1), 1.0)
        out = rgb.resize((int(rgb.width * scale), int(rgb.height * scale)), Image.Resampling.LANCZOS)
        out_path = path.with_name(f"{path.stem}_upscaled.png")
        out.save(out_path, "PNG")

    meta = path.with_name(f"{path.stem}_upscale_meta.txt")
    meta.write_text(
        "\n".join(
            [
                f"mode={mode}",
                f"target={target}",
                f"source={path}",
                f"esrgan_model_path={esrgan_model or 'unset'}",
                f"tiled_model_path={tiled_model or 'unset'}",
            ]
        ),
        encoding="utf-8",
    )
    return out_path
