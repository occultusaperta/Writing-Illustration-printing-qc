import base64
import threading
import time
from pathlib import Path

import requests

from bookforge.illustration.providers.flux_local_provider import FluxLocalImageProvider
from bookforge.illustration.providers.flux_local_service import run_flux_local_service
from bookforge.runtime.health import wait_for_health


def test_flux_local_service_generate_and_health(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_FLUX_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("BOOKFORGE_FLUX_RUNTIME_MODE", "fallback")
    port = 8199
    t = threading.Thread(target=run_flux_local_service, kwargs={"host": "127.0.0.1", "port": port}, daemon=True)
    t.start()
    health = wait_for_health(f"http://127.0.0.1:{port}/health", timeout_s=20, interval_s=0.2)
    assert health["status"] == "ok"
    assert health["runtime"]["runtime_mode"] == "fallback"
    assert health["runtime"]["ready"] is True

    payload = {
        "prompt": "fox under moon",
        "negative_prompt": "text",
        "width": 256,
        "height": 256,
        "seed": 123,
        "steps": 4,
        "guidance": 2.5,
        "quality_preset": "draft",
        "references": [],
        "variant_count": 1,
        "model_name": "black-forest-labs/FLUX.1-schnell",
    }
    resp = requests.post(f"http://127.0.0.1:{port}/generate", json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    assert data["provider"] == "flux_local"
    assert data["provenance"]["runtime_mode"] == "fallback"
    assert Path(data["image_path"]).exists()
    assert len(base64.b64decode(data["image_b64"])) > 100


def test_flux_local_provider_integration(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOOKFORGE_FLUX_OUTPUT_DIR", str(tmp_path / "outputs2"))
    monkeypatch.setenv("BOOKFORGE_FLUX_RUNTIME_MODE", "fallback")
    port = 8200
    t = threading.Thread(target=run_flux_local_service, kwargs={"host": "127.0.0.1", "port": port}, daemon=True)
    t.start()
    wait_for_health(f"http://127.0.0.1:{port}/health", timeout_s=20, interval_s=0.2)

    provider = FluxLocalImageProvider(url=f"http://127.0.0.1:{port}/generate")
    out = tmp_path / "page.png"
    provider.generate_option_image("a lighthouse", out, (256, 256), steps=4)
    assert out.exists() and out.stat().st_size > 100

    batch = requests.post(
        f"http://127.0.0.1:{port}/batch",
        json={"requests": [{"prompt": "a", "width": 128, "height": 128}, {"prompt": "b", "width": 128, "height": 128}]},
        timeout=20,
    )
    batch.raise_for_status()
    body = batch.json()
    assert len(body["results"]) == 2
