from __future__ import annotations

import base64
import io
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from PIL import Image

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.illustration.providers.flux_local_contract import FluxGenerateRequest, cache_key_for_request, parse_generate_response


class FluxLocalImageProvider:
    name = "flux_local"

    def __init__(self, url: str | None = None) -> None:
        raw = (url or os.getenv("BOOKFORGE_FLUX_LOCAL_URL") or "http://127.0.0.1:8188/generate").strip()
        self.url = raw
        if self.url.endswith("/generate"):
            self.base_url = self.url[: -len("/generate")]
        else:
            self.base_url = self.url.rstrip("/")
            self.url = f"{self.base_url}/generate"

    def health(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=8)
        resp.raise_for_status()
        return resp.json() if resp.content else {"status": "unknown"}

    def build_composite_reference(self, character_img: Path, style_img: Path, out_path: Path, palette_tile: Path | None = None) -> Path:
        return FalFluxIllustrator().build_composite_reference(character_img, style_img, out_path, palette_tile)

    def generate_option_image(self, prompt: str, out_path: Path, image_size_px: tuple[int, int], steps: int = 4) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = FluxGenerateRequest(
            prompt=prompt,
            width=image_size_px[0],
            height=image_size_px[1],
            steps=int(steps),
            quality_preset=str(os.getenv("BOOKFORGE_FLUX_QUALITY", "draft")),
        ).to_payload()
        png, _, _ = self._call_local_flux(payload)
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
        cache_hits: Dict[int, List[bool]] = {}
        cache_keys: Dict[int, List[str]] = {}
        provenance: Dict[int, List[Dict[str, Any]]] = {}
        for entry in page_prompts:
            page_no = int(entry["page_number"])
            prompt = str(entry["prompt"])
            page_seed = int((seeds or {}).get(page_no, 0)) if seeds else None
            page_paths: List[str] = []
            page_hits: List[bool] = []
            page_keys: List[str] = []
            page_prov: List[Dict[str, Any]] = []
            composite_ref = None
            if reference_image and style_image and reference_image.exists() and style_image.exists():
                composite_ref = variants_dir / f"_composite_ref_{page_no:03d}.png"
                self.build_composite_reference(reference_image, style_image, composite_ref, palette_tile)
            for idx in range(1, variants + 1):
                seed = (page_seed + idx - 1) if page_seed is not None else None
                payload = FluxGenerateRequest(
                    prompt=prompt,
                    width=image_size_px[0],
                    height=image_size_px[1],
                    steps=int(steps),
                    seed=seed,
                    quality_preset=str(os.getenv("BOOKFORGE_FLUX_QUALITY", "draft")),
                ).to_payload()
                if composite_ref or reference_image:
                    payload["reference_image"] = str(composite_ref or reference_image)
                key = cache_key_for_request(self.url, payload)
                png, from_cache, prov = self._call_local_flux(payload)
                out = variants_dir / f"page_{page_no:03d}_v{idx}.png"
                out.write_bytes(png)
                page_paths.append(str(out))
                page_hits.append(from_cache)
                page_keys.append(key)
                page_prov.append(prov)
            results[page_no] = page_paths
            cache_hits[page_no] = page_hits
            cache_keys[page_no] = page_keys
            provenance[page_no] = page_prov
        return {"provider": self.name, "variants": results, "endpoint": self.url, "cache_hits": cache_hits, "cache_keys": cache_keys, "provenance": provenance}

    def _call_local_flux(self, payload: Dict[str, Any], timeout_s: int = 120, retries: int = 2) -> tuple[bytes, bool, Dict[str, Any]]:
        ref_path = payload.get("reference_image")
        if ref_path and Path(ref_path).exists():
            with Image.open(Path(ref_path)) as ref:
                buff = io.BytesIO()
                ref.convert("RGB").save(buff, format="PNG")
            payload["reference_image"] = base64.b64encode(buff.getvalue()).decode("utf-8")

        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(self.url, json=payload, timeout=timeout_s)
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
                parsed = parse_generate_response(data)
                return base64.b64decode(parsed.image_b64), bool(data.get("cache_hit", False)), parsed.provenance
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(f"Flux local provider unavailable at {self.url}: {exc}") from exc
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(0.2)
                    continue
                raise RuntimeError(f"Flux local provider returned invalid payload from {self.url}: {exc}") from exc
        raise RuntimeError(f"Flux local request failed unexpectedly: {last_exc}")
