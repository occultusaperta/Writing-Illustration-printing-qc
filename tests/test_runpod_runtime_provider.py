from pathlib import Path

from PIL import Image

from bookforge.qc.gpu_batch_scoring import gpu_batch_scoring_enabled, score_candidate_batch
from bookforge.runtime.orchestration import RuntimeConfig, _resolve_provider, config_from_env
from bookforge.runtime.providers.runpod import RunPodRuntimeProvider


def test_runtime_config_from_env_runpod(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_RUNTIME_PROVIDER", "runpod")
    cfg = config_from_env()
    assert cfg.provider == "runpod"




def test_runtime_config_from_env_runpod_default_budget(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_RUNTIME_PROVIDER", "runpod")
    monkeypatch.delenv("BOOKFORGE_RUNTIME_MAX_HOURLY_USD", raising=False)
    cfg = config_from_env()
    assert cfg.max_hourly_usd == 0.0


def test_provider_resolution_runpod(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    cfg = RuntimeConfig(provider="runpod")
    provider = _resolve_provider(cfg)
    assert provider.name == "runpod"


def test_runpod_build_create_payload(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    p = RunPodRuntimeProvider()
    payload = p.build_create_payload(
        gpu_type_id="NVIDIA_B200_ID",
        disk_gb=80,
        image="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime",
        service_port=8188,
    )
    assert payload["gpuTypeId"] == "NVIDIA_B200_ID"
    assert payload["gpuCount"] == 1
    assert payload["containerDiskInGb"] == 80
    assert payload["ports"] == "22/tcp,8188/http"


def test_runpod_extract_ssh_connection(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    provider = RunPodRuntimeProvider()
    status = {
        "pod": {
            "runtime": {
                "ports": [
                    {"privatePort": 8188, "publicPort": 30100, "ip": "198.51.100.1"},
                    {"privatePort": 22, "publicPort": 30222, "ip": "198.51.100.1"},
                ]
            }
        }
    }
    ssh = provider.extract_ssh_connection(status)
    assert ssh["host"] == "198.51.100.1"
    assert ssh["port"] == 30222


def test_gpu_batch_scoring_api_shape_and_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BOOKFORGE_GPU_BATCH_SCORING", "true")
    monkeypatch.setattr("bookforge.qc.gpu_batch_scoring.torch", None)
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    Image.new("RGB", (64, 64), (120, 120, 120)).save(p1)
    Image.new("RGB", (64, 64), (80, 90, 100)).save(p2)

    assert gpu_batch_scoring_enabled() is True
    scores = score_candidate_batch([p1, p2])
    assert str(p1) in scores and str(p2) in scores
    for metrics in scores.values():
        assert set(metrics.keys()) == {
            "sharpness",
            "texture_density",
            "detail_density",
            "saliency_score",
            "composition_score",
            "ranking_score",
            "cuda_used",
        }
        assert metrics["cuda_used"] is False
        assert 0.0 <= metrics["ranking_score"] <= 1.0
