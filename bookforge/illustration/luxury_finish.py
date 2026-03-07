from __future__ import annotations

import os

from PIL import Image, ImageEnhance, ImageFilter


def _enabled() -> bool:
    return str(os.getenv("BOOKFORGE_LUXURY_FINISH", "false")).strip().lower() in {"1", "true", "yes", "on"}


def apply_microtexture_enhancement(image: Image.Image) -> Image.Image:
    if not _enabled():
        return image
    return image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))


def apply_canvas_grain(image: Image.Image) -> Image.Image:
    if not _enabled():
        return image
    softened = image.filter(ImageFilter.GaussianBlur(radius=0.25))
    return Image.blend(image, softened, alpha=0.06)


def apply_paint_variance(image: Image.Image) -> Image.Image:
    if not _enabled():
        return image
    sat = ImageEnhance.Color(image).enhance(1.03)
    return ImageEnhance.Contrast(sat).enhance(1.02)
