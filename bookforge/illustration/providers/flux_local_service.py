from __future__ import annotations

import argparse
import base64
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

from bookforge.illustration.providers.flux_local_contract import FluxGenerateRequest, cache_key_for_request


class FluxRuntimeAdapter:
    def __init__(self) -> None:
        self.output_dir = Path(os.getenv("BOOKFORGE_FLUX_OUTPUT_DIR", "./flux_outputs")).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model = os.getenv("BOOKFORGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")

    def _fallback_image(self, req: FluxGenerateRequest) -> Image.Image:
        img = Image.new("RGB", (req.width, req.height), (238, 234, 224))
        d = ImageDraw.Draw(img)
        d.rectangle((24, 24, req.width - 24, req.height - 24), outline=(80, 80, 80), width=4)
        d.text((42, 42), f"FLUX_LOCAL\nseed={req.seed or 0}\n{req.prompt[:140]}", fill=(20, 20, 20))
        return img

    def _diffusers_generate(self, req: FluxGenerateRequest) -> Image.Image:
        try:
            import torch
            from diffusers import FluxPipeline
        except Exception as exc:
            raise RuntimeError(f"Diffusers runtime unavailable: {exc}") from exc

        pipe = FluxPipeline.from_pretrained(req.model_name or self.model, torch_dtype=torch.bfloat16)
        pipe.enable_model_cpu_offload()
        generator = torch.Generator(device="cpu").manual_seed(req.seed or 0)
        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or None,
            guidance_scale=req.guidance or 2.5,
            num_inference_steps=req.steps,
            width=req.width,
            height=req.height,
            generator=generator,
        )
        return result.images[0]

    def generate(self, req: FluxGenerateRequest) -> Tuple[bytes, Dict[str, Any]]:
        started = time.perf_counter()
        mode = (os.getenv("BOOKFORGE_FLUX_RUNTIME_MODE") or "fallback").strip().lower()
        if mode == "diffusers":
            image = self._diffusers_generate(req)
            runtime = "diffusers"
        else:
            image = self._fallback_image(req)
            runtime = "fallback"

        buff = BytesIO()
        image.save(buff, format="PNG")
        png = buff.getvalue()
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        filename = f"flux_{int(time.time())}_{req.seed or 0}.png"
        output_path = self.output_dir / filename
        output_path.write_bytes(png)
        return png, {"runtime_mode": runtime, "elapsed_ms": elapsed_ms, "image_path": str(output_path), "model": req.model_name or self.model}


class FluxLocalServiceHandler(BaseHTTPRequestHandler):
    server_version = "BookforgeFluxLocal/0.2"
    adapter = FluxRuntimeAdapter()

    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "flux_local",
                    "supports": ["/generate", "/batch"],
                    "runtime_mode": os.getenv("BOOKFORGE_FLUX_RUNTIME_MODE", "fallback"),
                    "model": os.getenv("BOOKFORGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell"),
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError as exc:
            self._json(400, {"error": "invalid_json", "detail": str(exc)})
            return

        if self.path == "/generate":
            self._handle_generate(payload)
            return
        if self.path == "/batch":
            reqs = payload.get("requests", []) if isinstance(payload.get("requests"), list) else []
            results: List[Dict[str, Any]] = []
            for req in reqs:
                try:
                    results.append(self._generate(req))
                except Exception as exc:
                    results.append({"error": "generation_failed", "detail": str(exc)})
            self._json(200, {"results": results})
            return
        self._json(404, {"error": "not_found"})

    def _handle_generate(self, payload: Dict[str, Any]) -> None:
        try:
            self._json(200, self._generate(payload))
        except TimeoutError as exc:
            self._json(504, {"error": "generation_timeout", "detail": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:
            self._json(503, {"error": "runtime_unavailable", "detail": str(exc)})

    def _generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("Field 'prompt' is required")

        req = FluxGenerateRequest(
            prompt=prompt,
            negative_prompt=str(payload.get("negative_prompt", "")),
            width=int(payload.get("width", 1024)),
            height=int(payload.get("height", 1024)),
            seed=int(payload.get("seed", 0)) if payload.get("seed") is not None else None,
            steps=int(payload.get("steps", 4)),
            guidance=float(payload.get("guidance", 2.5)) if payload.get("guidance") is not None else None,
            quality_preset=str(payload.get("quality_preset", "draft")),
            references=[str(x) for x in (payload.get("references") or [])],
            lora_slots=payload.get("lora_slots") or [],
            spread=payload.get("spread") or {},
            variant_count=int(payload.get("variant_count", 1)),
            model_name=str(payload.get("model_name")) if payload.get("model_name") else None,
        )
        if req.width < 64 or req.height < 64:
            raise ValueError("Image width/height too small")

        key = cache_key_for_request("/generate", req.to_payload())
        timeout_s = int(os.getenv("BOOKFORGE_FLUX_REQUEST_TIMEOUT_S", "180"))
        started = time.perf_counter()
        png, meta = self.adapter.generate(req)
        if time.perf_counter() - started > timeout_s:
            raise TimeoutError(f"Generation exceeded timeout {timeout_s}s")

        b64 = base64.b64encode(png).decode("utf-8")
        return {
            "image_b64": b64,
            "image_path": meta["image_path"],
            "seed": req.seed or 0,
            "provider": "flux_local",
            "model": meta["model"],
            "elapsed_ms": meta["elapsed_ms"],
            "cache_key": key,
            "provenance": {
                "service": "flux_local_service",
                "runtime_mode": meta["runtime_mode"],
                "references": len(req.references),
                "variant_count": req.variant_count,
            },
        }


def run_flux_local_service(host: str = "127.0.0.1", port: int = 8188) -> None:
    HTTPServer((host, port), FluxLocalServiceHandler).serve_forever()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BookForge Flux local runtime service")
    parser.add_argument("--host", default=os.getenv("BOOKFORGE_FLUX_LOCAL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BOOKFORGE_FLUX_LOCAL_PORT", "8188")))
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_flux_local_service(host=args.host, port=args.port)
