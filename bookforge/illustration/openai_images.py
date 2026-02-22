from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

from bookforge.knowledge.loader import KnowledgeLoader


class OpenAIImagesIllustrator:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def generate(self, prompts: List[Dict[str, Any]], out_dir: Path, image_size_px: tuple[int, int]) -> Dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI illustration provider.")
        loaded = self.loader.load()
        out_dir.mkdir(parents=True, exist_ok=True)
        images: List[str] = []
        for p in prompts:
            png = self._generate_png(prompt=p["prompt"], api_key=api_key)
            path = out_dir / f"page_{p['page_number']:03d}.png"
            path.write_bytes(png)
            images.append(str(path))
        return {
            "provider": "openai-images",
            "images": images,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {"illustrator.provider": "openai-images"},
            "knowledge_docs_used": loaded["knowledge_docs_used"],
            "pdf_sources_used": loaded["pdf_sources_used"],
            "style_refs_used": loaded["style_refs_used"],
        }

    def _generate_png(self, prompt: str, api_key: str) -> bytes:
        url = "https://api.openai.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024"}

        last_error = None
        for attempt in range(1, 4):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=120)
                if r.status_code >= 400:
                    raise RuntimeError(f"OpenAI Images API error ({r.status_code}): {r.text[:300]}")
                data = r.json()
                b64 = data["data"][0].get("b64_json")
                if not b64:
                    raise RuntimeError("OpenAI response missing b64_json image payload.")
                return base64.b64decode(b64)
            except Exception as exc:
                last_error = exc
                time.sleep(attempt * 2)
        raise RuntimeError(f"OpenAI image generation failed after retries: {last_error}")
