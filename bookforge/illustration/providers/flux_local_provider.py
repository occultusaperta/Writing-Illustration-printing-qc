from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Dict, List

import requests
from PIL import Image

from bookforge.illustration.fal_flux import FalFluxIllustrator


class FluxLocalImageProvider:
    """Local Flux service provider.

    Expected API: POST {url} with json payload containing prompt/width/height/steps/seed/reference_image.
    Response must include either `image_b64` or `images[0].content`.
    """

    name = "flux_local"

    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.getenv("BOOKFORGE_FLUX_LOCAL_URL") or "http://127.0.0.1:8188/generate").strip()

    def build_composite_reference(self, character_img: Path, style_img: Path, out_path: Path, palette_tile: Path | None = None) -> Path:
        return FalFluxIllustrator().build_composite_reference(character_img, style_img, out_path, palette_tile)

    def generate_option_image(self, prompt: str, out_path: Path, image_size_px: tuple[int, int], steps: int = 4) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        png = self._call_local_flux(prompt, image_size_px[0], image_size_px[1], steps=steps)
        out_path.write_bytes(png)

    def generate_page_variants(
        self,
        page_prompts: List[Dict[str, Any]],
        variants_dir: Path,
        image_size_px: tuple[int, int],
        variants: int = 2,
        reference_image: Path | None = None,
        style_image: Path | None = None,
        palette_tile: Path | None = None,
        steps: int = 4,
        seeds: Dict[int, int] | None = None,
        cache_dir: Path | None = None,
    ) -> Dict[str, Any]:
        variants_dir.mkdir(parents=True, exist_ok=True)
        results: Dict[int, List[str]] = {}
        for entry in page_prompts:
            page_no = int(entry["page_number"])
            prompt = str(entry["prompt"])
            page_seed = int((seeds or {}).get(page_no, 0)) if seeds else None
            page_paths: List[str] = []
            composite_ref = None
            if reference_image and style_image and reference_image.exists() and style_image.exists():
                composite_ref = variants_dir / f"_composite_ref_{page_no:03d}.png"
                self.build_composite_reference(reference_image, style_image, composite_ref, palette_tile)
            for idx in range(1, variants + 1):
                seed = (page_seed + idx - 1) if page_seed is not None else None
                png = self._call_local_flux(prompt, image_size_px[0], image_size_px[1], steps=steps, seed=seed, reference_image=composite_ref or reference_image)
                out = variants_dir / f"page_{page_no:03d}_v{idx}.png"
                out.write_bytes(png)
                page_paths.append(str(out))
            results[page_no] = page_paths
        return {"provider": self.name, "variants": results, "endpoint": self.url, "cache_hits": {}, "cache_keys": {}}

    def _call_local_flux(self, prompt: str, width: int, height: int, steps: int = 4, seed: int | None = None, reference_image: Path | None = None) -> bytes:
        payload: Dict[str, Any] = {"prompt": prompt, "width": width, "height": height, "steps": int(steps)}
        if seed is not None:
            payload["seed"] = int(seed)
        if reference_image and reference_image.exists():
            with Image.open(reference_image) as ref:
                buff = io.BytesIO()
                ref.convert("RGB").save(buff, format="PNG")
            payload["reference_image"] = base64.b64encode(buff.getvalue()).decode("utf-8")
        try:
            resp = requests.post(self.url, json=payload, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Flux local provider unavailable at {self.url}: {exc}") from exc

        data = resp.json() if resp.content else {}
        direct = data.get("image_b64")
        nested = data.get("images", [{}])[0].get("content") if isinstance(data.get("images"), list) else None
        if direct:
            return base64.b64decode(direct)
        if nested:
            return base64.b64decode(nested)
        raise RuntimeError(f"Flux local provider returned no image payload from {self.url}.")
