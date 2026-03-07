from pathlib import Path

from bookforge.runtime.orchestration import RuntimeConfig, config_from_env
from bookforge.runtime.providers.vast_ai import VastAIRuntimeProvider
from bookforge.runtime.ssh import build_ssh_command


def test_runtime_config_from_env(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_RUNTIME_PROVIDER", "vast_ai")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_MAX_HOURLY_USD", "0.8")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_MIN_GPU_RAM_GB", "24")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_DISK_GB", "120")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_SSH_USER", "ubuntu")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_SSH_KEY_PATH", "~/.ssh/id_rsa")
    monkeypatch.setenv("BOOKFORGE_RUNTIME_SERVICE_PORT", "9999")
    cfg = config_from_env()
    assert cfg.provider == "vast_ai"
    assert cfg.max_hourly_usd == 0.8
    assert cfg.min_gpu_ram_gb == 24
    assert cfg.disk_gb == 120
    assert cfg.ssh_user == "ubuntu"
    assert cfg.ssh_key_path == "~/.ssh/id_rsa"
    assert cfg.service_port == 9999


def test_vast_payload_builders(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_VAST_API_KEY", "test")
    provider = VastAIRuntimeProvider()
    search = provider.build_search_payload(max_hourly_usd=1.1, min_gpu_ram_gb=16)
    assert search["dph_total"]["lte"] == 1.1
    assert search["gpu_ram"]["gte"] == 16

    create = provider.build_create_payload(offer_id="123", disk_gb=100, image="x/y:z")
    assert create["ask_id"] == 123
    assert create["disk"] == 100
    assert create["image"] == "x/y:z"


def test_build_ssh_command():
    cmd = build_ssh_command(host="1.2.3.4", user="root", port=2202, key_path="~/.ssh/key", remote_command="echo hi")
    rendered = " ".join(cmd)
    assert "ssh" in cmd[0]
    assert "-p 2202" in rendered
    assert "root@1.2.3.4" in rendered
    assert "echo hi" in rendered
