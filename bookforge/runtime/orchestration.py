from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from bookforge.runtime.health import wait_for_health
from bookforge.runtime.providers.base import RuntimeInstance, RuntimeProvider
from bookforge.runtime.providers.runpod import RunPodRuntimeProvider
from bookforge.runtime.providers.vast_ai import VastAIRuntimeProvider
from bookforge.runtime.ssh import copy_file_to_remote, run_ssh_command


@dataclass
class RuntimeConfig:
    provider: str = "vast_ai"
    max_hourly_usd: float = 1.2
    min_gpu_ram_gb: int = 16
    disk_gb: int = 80
    ssh_user: str = "root"
    ssh_key_path: str = ""
    service_port: int = 8188
    state_path: str = ".bookforge_runtime.json"


def config_from_env() -> RuntimeConfig:
    return RuntimeConfig(
        provider=(os.getenv("BOOKFORGE_RUNTIME_PROVIDER") or "vast_ai").strip().lower(),
        max_hourly_usd=float(os.getenv("BOOKFORGE_RUNTIME_MAX_HOURLY_USD") or "1.2"),
        min_gpu_ram_gb=int(os.getenv("BOOKFORGE_RUNTIME_MIN_GPU_RAM_GB") or "16"),
        disk_gb=int(os.getenv("BOOKFORGE_RUNTIME_DISK_GB") or "80"),
        ssh_user=(os.getenv("BOOKFORGE_RUNTIME_SSH_USER") or "root").strip(),
        ssh_key_path=(os.getenv("BOOKFORGE_RUNTIME_SSH_KEY_PATH") or "").strip(),
        service_port=int(os.getenv("BOOKFORGE_RUNTIME_SERVICE_PORT") or "8188"),
        state_path=(os.getenv("BOOKFORGE_RUNTIME_STATE_PATH") or ".bookforge_runtime.json").strip(),
    )


def _resolve_provider(cfg: RuntimeConfig) -> RuntimeProvider:
    if cfg.provider == "vast_ai":
        return VastAIRuntimeProvider()
    if cfg.provider == "runpod":
        return RunPodRuntimeProvider()
    raise RuntimeError(f"Unsupported runtime provider: {cfg.provider}")


class RuntimeOrchestrator:
    def __init__(self, cfg: RuntimeConfig | None = None) -> None:
        self.cfg = cfg or config_from_env()
        self.provider = _resolve_provider(self.cfg)

    def provision(self) -> Dict[str, Any]:
        offers = self.provider.list_offers(max_hourly_usd=self.cfg.max_hourly_usd, min_gpu_ram_gb=self.cfg.min_gpu_ram_gb)
        if not offers:
            raise RuntimeError("No rentable GPU offers matched budget and VRAM filters.")
        if self.cfg.provider == "runpod":
            b200 = [o for o in offers if o.gpu_name.strip().lower() == "nvidia b200"]
            if not b200:
                raise RuntimeError("RunPod did not return a NVIDIA B200 GPU type.")
            selected = b200[0]
        else:
            selected = offers[0]
        instance = self.provider.create_instance(offer_id=selected.offer_id, disk_gb=self.cfg.disk_gb)
        payload = {"status": "ok", "offer": asdict(selected), "instance": asdict(instance), "config": asdict(self.cfg)}
        self._write_state(payload)
        return payload

    def bootstrap(self, *, host: str, port: int | None = None, user: str | None = None) -> Dict[str, Any]:
        ssh_port = port or 22
        ssh_user = user or self.cfg.ssh_user
        root = Path(__file__).resolve().parent
        scripts = [
            root / "bootstrap" / "bootstrap_gpu_host.sh",
            root / "bootstrap" / "install_flux_runtime.sh",
        ]
        remote_dir = "/tmp/bookforge_runtime"
        run_ssh_command(host=host, user=ssh_user, port=ssh_port, key_path=self.cfg.ssh_key_path, remote_command=f"mkdir -p {remote_dir}")
        for script in scripts:
            copy_file_to_remote(local_path=str(script), remote_path=f"{remote_dir}/{script.name}", host=host, user=ssh_user, port=ssh_port, key_path=self.cfg.ssh_key_path)
            run_ssh_command(
                host=host,
                user=ssh_user,
                port=ssh_port,
                key_path=self.cfg.ssh_key_path,
                remote_command=f"chmod +x {remote_dir}/{script.name} && sudo {remote_dir}/{script.name}",
                timeout_s=900,
            )
        return {"status": "ok", "host": host, "scripts": [s.name for s in scripts]}

    def launch_service(self, *, host: str, port: int | None = None, user: str | None = None, model_name: str | None = None) -> Dict[str, Any]:
        ssh_port = port or 22
        ssh_user = user or self.cfg.ssh_user
        service_port = self.cfg.service_port
        model = model_name or os.getenv("BOOKFORGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")
        cmd = (
            "mkdir -p ~/bookforge_runtime && "
            "source ~/bookforge_runtime/venv/bin/activate && "
            f"export BOOKFORGE_FLUX_MODEL={model} && "
            f"nohup python -m bookforge.illustration.providers.flux_local_service --host 0.0.0.0 --port {service_port} "
            "> ~/bookforge_runtime/flux_local.log 2>&1 &"
        )
        run_ssh_command(host=host, user=ssh_user, port=ssh_port, key_path=self.cfg.ssh_key_path, remote_command=cmd, timeout_s=180)
        health = wait_for_health(f"http://{host}:{service_port}/health", timeout_s=300, interval_s=5)
        return {"status": "ok", "health": health, "url": f"http://{host}:{service_port}/generate"}

    def stop(self, *, instance_id: str) -> Dict[str, Any]:
        resp = self.provider.stop_instance(instance_id=instance_id)
        return {"status": "ok", "result": resp, "instance_id": instance_id}

    def destroy(self, *, instance_id: str) -> Dict[str, Any]:
        resp = self.provider.destroy_instance(instance_id=instance_id)
        return {"status": "ok", "result": resp, "instance_id": instance_id}

    def status(self, *, instance_id: str) -> Dict[str, Any]:
        resp = self.provider.instance_status(instance_id=instance_id)
        return {"status": "ok", "result": resp, "instance_id": instance_id}

    def _write_state(self, payload: Dict[str, Any]) -> None:
        Path(self.cfg.state_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_runtime_state(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
