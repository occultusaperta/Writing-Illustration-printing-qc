from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont

from bookforge.knowledge.loader import KnowledgeLoader


class FalFluxIllustrator:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def generate(self, prompts: List[Dict[str, Any]], out_dir: Path, image_size_px: tuple[int, int]) -> Dict[str, Any]:
        loaded = self.loader.load()
        out_dir.mkdir(parents=True, exist_ok=True)
        fal_key = os.getenv("FAL_KEY", "").strip()

        images = []
        if fal_key:
            # Placeholder for real Fal call; still resilient in local mode.
            # In v1, we keep local placeholder output deterministic.
            provider = "fal_stub_with_key"
        else:
            provider = "placeholder"

        for p in prompts:
            path = out_dir / f"page_{p['page_number']:03d}.png"
            self._make_placeholder(path, image_size_px, p["caption"])
            images.append(str(path))

        return {
            "provider": provider,
            "images": images,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {
                "visual_modes.visual_modes": list(loaded["knowledge"]["visual_modes"]["visual_modes"].keys())
            },
            "pdf_sources_used": loaded["pdf_sources_used"],
        }

    def _make_placeholder(self, path: Path, size: tuple[int, int], caption: str) -> None:
        width, height = size
        img = Image.new("RGB", size)
        draw = ImageDraw.Draw(img)
        for y in range(height):
            r = int(245 - (y / max(height - 1, 1)) * 60)
            g = int(250 - (y / max(height - 1, 1)) * 40)
            b = 255
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        margin = int(min(width, height) * 0.05)
        draw.rectangle([margin, margin, width - margin, height - margin], outline=(30, 30, 30), width=6)

        font = ImageFont.load_default()
        text = caption[:120]
        draw.text((margin + 20, height - margin - 35), text, fill=(20, 20, 20), font=font)
        img.save(path, "PNG")
