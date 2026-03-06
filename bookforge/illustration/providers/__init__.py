from __future__ import annotations

import os

from bookforge.illustration.providers.base import ImageProvider
from bookforge.illustration.providers.fal_provider import FalImageProvider
from bookforge.illustration.providers.flux_local_provider import FluxLocalImageProvider

OPENAI_DISABLED_MESSAGE = "OpenAI image provider disabled; Fal/Flux only."


def resolve_image_provider(requested: str = "auto", *, fal_endpoint: str | None = None) -> tuple[ImageProvider, str]:
    raw = (requested or "auto").strip().lower()
    if raw == "openai":
        raise RuntimeError(OPENAI_DISABLED_MESSAGE)
    env_choice = (os.getenv("BOOKFORGE_IMAGE_PROVIDER") or "auto").strip().lower()
    if env_choice == "openai":
        raise RuntimeError(OPENAI_DISABLED_MESSAGE)

    chosen = raw if raw != "auto" else env_choice
    if chosen == "auto":
        chosen = "flux_local" if os.getenv("BOOKFORGE_FLUX_LOCAL_URL") else "fal"

    if chosen == "fal":
        return FalImageProvider(endpoint=fal_endpoint or "https://fal.run/fal-ai/flux/schnell"), "fal"
    if chosen == "flux_local":
        return FluxLocalImageProvider(), "flux_local"

    raise RuntimeError(f"Unsupported image provider: {chosen}. Use auto/fal/flux_local.")


__all__ = ["ImageProvider", "FalImageProvider", "FluxLocalImageProvider", "resolve_image_provider", "OPENAI_DISABLED_MESSAGE"]
