from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

from bookforge.runtime.health import check_http_health, wait_for_health
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
    provider = (os.getenv("BOOKFORGE_RUNTIME_PROVIDER") or "vast_ai").strip().lower()
    default_max_hourly = "0" if provider == "runpod" else "1.2"
    return RuntimeConfig(
        provider=provider,
        max_hourly_usd=float(os.getenv("BOOKFORGE_RUNTIME_MAX_HOURLY_USD") or default_max_hourly),
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
        if self.cfg.provider == "runpod":
            offers = self.provider.list_offers(max_hourly_usd=0, min_gpu_ram_gb=self.cfg.min_gpu_ram_gb)
        else:
            offers = self.provider.list_offers(max_hourly_usd=self.cfg.max_hourly_usd, min_gpu_ram_gb=self.cfg.min_gpu_ram_gb)
        if not offers:
            raise RuntimeError("No rentable GPU offers matched budget and VRAM filters.")
        if self.cfg.provider == "runpod":
            b200 = [o for o in offers if o.gpu_name.strip().lower() == "nvidia b200"]
            if not b200:
                raise RuntimeError("RunPod did not return a NVIDIA B200 GPU type.")
            selected = b200[0]
            if self.cfg.max_hourly_usd > 0 and selected.price_per_hour > self.cfg.max_hourly_usd:
                raise RuntimeError(
                    f"Selected RunPod B200 price ${selected.price_per_hour:.3f}/hr exceeds "
                    f"BOOKFORGE_RUNTIME_MAX_HOURLY_USD={self.cfg.max_hourly_usd:.3f}. "
                    "Set budget to 0 to disable cap."
                )
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
                remote_command=f"chmod +x {remote_dir}/{script.name} && {remote_dir}/{script.name}",
                timeout_s=900,
            )
        return {"status": "ok", "host": host, "scripts": [s.name for s in scripts]}

    def launch_service(
        self,
        *,
        host: str,
        port: int | None = None,
        user: str | None = None,
        model_name: str | None = None,
        runtime_mode: str | None = None,
    ) -> Dict[str, Any]:
        ssh_port = port or 22
        ssh_user = user or self.cfg.ssh_user
        service_port = self.cfg.service_port
        model = model_name or os.getenv("BOOKFORGE_FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")
        mode = (runtime_mode or os.getenv("BOOKFORGE_FLUX_RUNTIME_MODE") or "diffusers").strip().lower()
        cmd = (
            "mkdir -p ~/bookforge_runtime && "
            "source ~/bookforge_runtime/venv/bin/activate && "
            f"export BOOKFORGE_FLUX_MODEL={model} && "
            f"export BOOKFORGE_FLUX_RUNTIME_MODE={mode} && "
            f"nohup python -m bookforge.illustration.providers.flux_local_service --host 0.0.0.0 --port {service_port} "
            "> ~/bookforge_runtime/flux_local.log 2>&1 &"
        )
        run_ssh_command(host=host, user=ssh_user, port=ssh_port, key_path=self.cfg.ssh_key_path, remote_command=cmd, timeout_s=180)
        try:
            health_url = f"http://{host}:{service_port}/health"
            health = wait_for_health(health_url, timeout_s=300, interval_s=5)
            health_runtime = (health.get("runtime") or {}) if isinstance(health, dict) else {}
            if mode == "diffusers" and health_runtime.get("ready") is False:
                issues = ", ".join(str(x) for x in (health_runtime.get("issues") or []))
                raise RuntimeError(f"runtime reported diffusers not ready: {issues or 'unknown issue'}")
            health = check_http_health(health_url, timeout_s=8)
        except Exception as exc:
            log_tail = run_ssh_command(
                host=host,
                user=ssh_user,
                port=ssh_port,
                key_path=self.cfg.ssh_key_path,
                remote_command="tail -n 80 ~/bookforge_runtime/flux_local.log || true",
                timeout_s=30,
            )
            raise RuntimeError(f"runtime-launch health check failed: {exc}\n--- remote flux_local.log tail ---\n{log_tail}") from exc
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
