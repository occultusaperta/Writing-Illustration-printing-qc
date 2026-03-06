from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

from PIL import Image, ImageDraw

from bookforge.illustration.providers.flux_local_contract import cache_key_for_request


class FluxLocalServiceHandler(BaseHTTPRequestHandler):
    server_version = "BookforgeFluxLocal/0.1"

    def _json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "service": "flux_local", "supports": ["/generate", "/batch"]})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8")) if raw else {}

        if self.path == "/generate":
            self._json(200, self._generate(payload))
            return
        if self.path == "/batch":
            reqs = payload.get("requests", []) if isinstance(payload.get("requests"), list) else []
            self._json(200, {"results": [self._generate(req) for req in reqs]})
            return
        self._json(404, {"error": "not_found"})

    def _generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        width = int(payload.get("width", 1024))
        height = int(payload.get("height", 1024))
        prompt = str(payload.get("prompt", ""))
        seed = int(payload.get("seed", 0))

        img = Image.new("RGB", (width, height), (238, 234, 224))
        d = ImageDraw.Draw(img)
        d.rectangle((24, 24, width - 24, height - 24), outline=(80, 80, 80), width=4)
        d.text((42, 42), f"FLUX_LOCAL_STUB\nseed={seed}\n{prompt[:120]}", fill=(20, 20, 20))

        buff = BytesIO()
        img.save(buff, format="PNG")
        b64 = base64.b64encode(buff.getvalue()).decode("utf-8")
        key = cache_key_for_request("/generate", payload)
        return {
            "image_b64": b64,
            "seed": seed,
            "provider": "flux_local",
            "model": "flux_stub",
            "elapsed_ms": 10,
            "cache_key": key,
            "provenance": {"service": "stub", "notes": "Replace with real Flux server on runtime machine."},
        }


def run_flux_local_service(host: str = "127.0.0.1", port: int = 8188) -> None:
    HTTPServer((host, port), FluxLocalServiceHandler).serve_forever()


if __name__ == "__main__":
    run_flux_local_service()
