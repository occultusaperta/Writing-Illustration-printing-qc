from __future__ import annotations

import base64
import hashlib
import io
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from PIL import Image


class FalFluxIllustrator:
    """Fal+Flux-only image generator with optional reference-image fallback."""

    def __init__(self, endpoint: str = "https://fal.run/fal-ai/flux/schnell") -> None:
        self.endpoint = endpoint

    def build_composite_reference(self, character_img: Path, style_img: Path, out_path: Path, palette_tile: Path | None = None) -> Path:
        with Image.open(character_img) as c_im, Image.open(style_img) as s_im:
            c_rgb = c_im.convert("RGB")
            s_rgb = s_im.convert("RGB")
            target_h = min(c_rgb.height, s_rgb.height)
            c_resized = c_rgb.resize((int(c_rgb.width * target_h / c_rgb.height), target_h), Image.Resampling.LANCZOS)
            s_resized = s_rgb.resize((int(s_rgb.width * target_h / s_rgb.height), target_h), Image.Resampling.LANCZOS)
            palette_h = 0
            palette_img = None
            if palette_tile and palette_tile.exists():
                with Image.open(palette_tile) as p_im:
                    palette_img = p_im.convert("RGB")
                    palette_h = max(48, int(target_h * 0.12))
                    palette_img = palette_img.resize((c_resized.width + s_resized.width, palette_h), Image.Resampling.LANCZOS)
            out = Image.new("RGB", (c_resized.width + s_resized.width, target_h + palette_h), (245, 243, 238))
            out.paste(c_resized, (0, 0))
            out.paste(s_resized, (c_resized.width, 0))
            if palette_img is not None:
                out.paste(palette_img, (0, target_h))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out.save(out_path, "PNG")
        return out_path

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
        fal_key = os.getenv("FAL_KEY", "").strip()
        if not fal_key:
            raise RuntimeError("FAL_KEY is required for Fal/Flux illustration provider.")
        variants_dir.mkdir(parents=True, exist_ok=True)

        results: Dict[int, List[str]] = {}
        cache_hits: Dict[int, List[bool]] = {}
        for entry in page_prompts:
            page_no = int(entry["page_number"])
            prompt = entry["prompt"]
            generated: List[str] = []
            composite_ref = None
            if reference_image and style_image and reference_image.exists() and style_image.exists():
                composite_ref = variants_dir / f"_composite_ref_{page_no:03d}.png"
                self.build_composite_reference(reference_image, style_image, composite_ref, palette_tile)
            page_seed = int((seeds or {}).get(page_no, 0)) if seeds else None
            page_hits: List[bool] = []
            for variant_idx in range(1, variants + 1):
                seed = (page_seed + variant_idx - 1) if page_seed is not None else None
                out = variants_dir / f"page_{page_no:03d}_v{variant_idx}.png"
                key = None
                if cache_dir is not None and seed is not None:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    payload = f"{prompt}|{self.endpoint}|{seed}|{image_size_px[0]}x{image_size_px[1]}".encode("utf-8")
                    key = hashlib.sha256(payload).hexdigest()
                    cached = cache_dir / f"{key}.png"
                    if cached.exists():
                        out.write_bytes(cached.read_bytes())
                        generated.append(str(out))
                        page_hits.append(True)
                        continue
                png = self._call_fal_flux(
                    prompt=prompt,
                    width=image_size_px[0],
                    height=image_size_px[1],
                    fal_key=fal_key,
                    reference_image=composite_ref or reference_image,
                    steps=steps,
                    seed=seed,
                )
                out.write_bytes(png)
                if cache_dir is not None and key is not None:
                    (cache_dir / f"{key}.png").write_bytes(png)
                generated.append(str(out))
                page_hits.append(False)
            results[page_no] = generated
            cache_hits[page_no] = page_hits
        return {"provider": "fal-flux", "variants": results, "endpoint": self.endpoint, "cache_hits": cache_hits}

    def generate_option_image(self, prompt: str, out_path: Path, image_size_px: tuple[int, int], steps: int = 4) -> None:
        fal_key = os.getenv("FAL_KEY", "").strip()
        if not fal_key:
            raise RuntimeError("FAL_KEY is required for Fal/Flux illustration provider.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        png = self._call_fal_flux(prompt, image_size_px[0], image_size_px[1], fal_key=fal_key, steps=steps)
        out_path.write_bytes(png)

    def _call_fal_flux(self, prompt: str, width: int, height: int, fal_key: str, reference_image: Path | None = None, steps: int = 4, seed: int | None = None) -> bytes:
        headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {"prompt": prompt, "image_size": {"width": width, "height": height}, "num_inference_steps": steps}
        if seed is not None:
            payload["seed"] = int(seed)
        ref_b64: str | None = None
        if reference_image and reference_image.exists():
            with Image.open(reference_image) as ref:
                rgb = ref.convert("RGB")
                buff = io.BytesIO()
                rgb.save(buff, format="PNG")
                ref_b64 = base64.b64encode(buff.getvalue()).decode("utf-8")

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                if ref_b64:
                    payload_with_ref = dict(payload)
                    payload_with_ref["image_prompt"] = f"data:image/png;base64,{ref_b64}"
                    resp = requests.post(self.endpoint, headers=headers, json=payload_with_ref, timeout=120)
                    if resp.status_code < 400:
                        return self._extract_image_bytes(resp)
                resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=120)
                if resp.status_code >= 400:
                    if seed is not None and ("seed" in resp.text.lower() or resp.status_code in {400, 422}):
                        payload_without_seed = dict(payload)
                        payload_without_seed.pop("seed", None)
                        resp = requests.post(self.endpoint, headers=headers, json=payload_without_seed, timeout=120)
                        if resp.status_code < 400:
                            return self._extract_image_bytes(resp)
                    raise RuntimeError(f"Fal API error ({resp.status_code}): {resp.text[:300]}")
                return self._extract_image_bytes(resp)
            except Exception as exc:
                last_error = exc
                time.sleep(attempt * 2)
        raise RuntimeError(f"Fal/Flux generation failed after retries: {last_error}")

    def _extract_image_bytes(self, response: requests.Response) -> bytes:
        data = response.json()
        image_b64 = data.get("images", [{}])[0].get("content")
        image_url = data.get("images", [{}])[0].get("url")
        if image_b64:
            return base64.b64decode(image_b64)
        if image_url:
            img_r = requests.get(image_url, timeout=120)
            img_r.raise_for_status()
            return img_r.content
        raise RuntimeError("Fal API response did not include image content.")
