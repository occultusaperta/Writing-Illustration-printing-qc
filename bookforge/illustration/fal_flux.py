from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from PIL import Image, ImageDraw, ImageFont

from bookforge.knowledge.loader import KnowledgeLoader


class FalFluxIllustrator:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def generate(self, prompts: List[Dict[str, Any]], out_dir: Path, image_size_px: tuple[int, int]) -> Dict[str, Any]:
        fal_key = os.getenv("FAL_KEY", "").strip()
        if not fal_key:
            raise RuntimeError("FAL_KEY is required for Fal/Flux illustration provider.")

        loaded = self.loader.load()
        out_dir.mkdir(parents=True, exist_ok=True)
        images: List[str] = []
        w, h = image_size_px
        for p in prompts:
            prompt = p["prompt"]
            img_bytes = self._call_fal_flux(prompt=prompt, width=w, height=h, fal_key=fal_key)
            path = out_dir / f"page_{p['page_number']:03d}.png"
            path.write_bytes(img_bytes)
            images.append(str(path))

        return {
            "provider": "fal-flux",
            "images": images,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {"illustrator.provider": "fal-flux"},
            "knowledge_docs_used": loaded["knowledge_docs_used"],
            "pdf_sources_used": loaded["pdf_sources_used"],
            "style_refs_used": loaded["style_refs_used"],
        }

    def _call_fal_flux(self, prompt: str, width: int, height: int, fal_key: str) -> bytes:
        url = "https://fal.run/fal-ai/flux/schnell"
        headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
        payload = {"prompt": prompt, "image_size": {"width": width, "height": height}, "num_inference_steps": 4}

        last_error = None
        for attempt in range(1, 4):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=120)
                if r.status_code >= 400:
                    raise RuntimeError(f"Fal API error ({r.status_code}): {r.text[:300]}")
                data = r.json()
                image_b64 = data.get("images", [{}])[0].get("content")
                image_url = data.get("images", [{}])[0].get("url")
                if image_b64:
                    return base64.b64decode(image_b64)
                if image_url:
                    img_r = requests.get(image_url, timeout=120)
                    img_r.raise_for_status()
                    return img_r.content
                raise RuntimeError("Fal API response did not include image content.")
            except Exception as exc:
                last_error = exc
                time.sleep(attempt * 2)
        raise RuntimeError(f"Fal/Flux generation failed after retries: {last_error}")


class PlaceholderIllustrator:
    def generate(self, prompts: List[Dict[str, Any]], out_dir: Path, image_size_px: tuple[int, int]) -> Dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        images: List[str] = []
        for p in prompts:
            path = out_dir / f"page_{p['page_number']:03d}.png"
            self._make_placeholder(path, image_size_px, p.get("caption", ""))
            images.append(str(path))
        return {"provider": "placeholder", "images": images, "placeholder": True}

    def _make_placeholder(self, path: Path, size: tuple[int, int], caption: str) -> None:
        width, height = size
        img = Image.new("RGB", size, color=(248, 248, 248))
        draw = ImageDraw.Draw(img)
        draw.rectangle((20, 20, width - 20, height - 20), outline=(180, 0, 0), width=8)
        draw.text((40, 40), "PLACEHOLDER", fill=(180, 0, 0), font=ImageFont.load_default())
        draw.text((40, 80), caption[:120], fill=(20, 20, 20), font=ImageFont.load_default())
        img.save(path, "PNG")
