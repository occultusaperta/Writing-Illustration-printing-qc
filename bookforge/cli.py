from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from bookforge.pipeline import BookforgePipeline
from bookforge.runtime.orchestration import RuntimeOrchestrator, config_from_env, load_runtime_state


def main() -> None:
    parser = argparse.ArgumentParser(description="BookForge KDP Premium Studio CLI")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="Validate Fal-only setup")
    doctor.add_argument("--strict", action="store_true")

    preprod = sub.add_parser("preprod", help="Generate character/style options for approval")
    preprod.add_argument("--story", required=True)
    preprod.add_argument("--out", required=True)
    preprod.add_argument("--size", default="8.5x8.5")
    preprod.add_argument("--pages", type=int, default=24)
    preprod.add_argument("--variants", type=int, default=4)
    preprod.add_argument("--profile")

    lock = sub.add_parser("lock", help="Freeze approved character and style")
    lock.add_argument("--out", required=True)
    lock.add_argument("--size", default="8.5x8.5")
    lock.add_argument("--pages", type=int, default=24)

    studio = sub.add_parser("studio", help="Generate full package after lock")
    studio.add_argument("--story", required=True)
    studio.add_argument("--out", required=True)
    studio.add_argument("--size", default="8.5x8.5")
    studio.add_argument("--pages", type=int, default=24)
    studio.add_argument("--illustrator", choices=["auto", "fal", "flux_local", "openai"], default="auto")
    studio.add_argument("--require-lock", action="store_true")

    verify = sub.add_parser("verify", help="Validate studio artifacts and package contents")
    verify.add_argument("--out", required=True)

    ui = sub.add_parser("ui", help="Launch local Streamlit UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8501)

    runtime_provision = sub.add_parser("runtime-provision", help="Provision rented GPU runtime using env credentials")
    runtime_provision.add_argument("--max-hourly-usd", type=float)
    runtime_provision.add_argument("--min-gpu-ram-gb", type=int)

    runtime_bootstrap = sub.add_parser("runtime-bootstrap", help="Bootstrap runtime host over SSH")
    runtime_bootstrap.add_argument("--host")
    runtime_bootstrap.add_argument("--ssh-port", type=int, default=22)
    runtime_bootstrap.add_argument("--ssh-user")

    runtime_launch = sub.add_parser("runtime-launch", help="Launch flux_local service on runtime host")
    runtime_launch.add_argument("--host")
    runtime_launch.add_argument("--ssh-port", type=int, default=22)
    runtime_launch.add_argument("--ssh-user")
    runtime_launch.add_argument("--model")
    runtime_launch.add_argument("--runtime-mode", choices=["fallback", "diffusers"])

    runtime_health = sub.add_parser("runtime-health", help="Check runtime provider status and service health")
    runtime_health.add_argument("--instance-id")
    runtime_health.add_argument("--url")

    runtime_stop = sub.add_parser("runtime-stop", help="Stop provisioned runtime instance")
    runtime_stop.add_argument("--instance-id")

    runtime_destroy = sub.add_parser("runtime-destroy", help="Destroy provisioned runtime instance")
    runtime_destroy.add_argument("--instance-id")

    args = parser.parse_args()
    pipeline = BookforgePipeline()

    try:
        runtime_cfg = config_from_env()
        runtime_state = load_runtime_state(runtime_cfg.state_path)
        if args.command == "doctor":
            result = pipeline.doctor(strict=args.strict)
        elif args.command == "preprod":
            result = pipeline.preprod(args.story, args.out, args.size, args.pages, args.variants, args.profile)
        elif args.command == "lock":
            result = pipeline.lock(args.out, args.size, args.pages)
        elif args.command == "studio":
            result = pipeline.studio(args.story, args.out, args.size, args.pages, args.illustrator, args.require_lock)
        elif args.command == "verify":
            result = pipeline.verify(args.out)
        elif args.command == "ui":
            if importlib.util.find_spec("streamlit") is None:
                print("UI extras not installed. Run: pip install -e '.[ui]'")
                sys.exit(1)
            cmd = [
                "streamlit",
                "run",
                "-m",
                "bookforge.ui.app",
                "--server.address",
                args.host,
                "--server.port",
                str(args.port),
            ]
            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                fallback = [
                    "streamlit",
                    "run",
                    str((Path(__file__).parent / "ui" / "app.py").resolve()),
                    "--server.address",
                    args.host,
                    "--server.port",
                    str(args.port),
                ]
                proc = subprocess.run(fallback)
            sys.exit(proc.returncode)
        elif args.command == "runtime-provision":
            orch = RuntimeOrchestrator(runtime_cfg)
            if args.max_hourly_usd is not None:
                orch.cfg.max_hourly_usd = args.max_hourly_usd
            if args.min_gpu_ram_gb is not None:
                orch.cfg.min_gpu_ram_gb = args.min_gpu_ram_gb
            result = orch.provision()
        elif args.command == "runtime-bootstrap":
            host = args.host or runtime_state.get("instance", {}).get("host")
            if not host:
                raise RuntimeError("runtime-bootstrap requires --host or saved runtime state with host")
            orch = RuntimeOrchestrator(runtime_cfg)
            result = orch.bootstrap(host=host, port=args.ssh_port, user=args.ssh_user)
        elif args.command == "runtime-launch":
            host = args.host or runtime_state.get("instance", {}).get("host")
            if not host:
                raise RuntimeError("runtime-launch requires --host or saved runtime state with host")
            orch = RuntimeOrchestrator(runtime_cfg)
            result = orch.launch_service(
                host=host,
                port=args.ssh_port,
                user=args.ssh_user,
                model_name=args.model,
                runtime_mode=args.runtime_mode,
            )
        elif args.command == "runtime-health":
            orch = RuntimeOrchestrator(runtime_cfg)
            instance_id = args.instance_id or runtime_state.get("instance", {}).get("instance_id")
            result = {}
            if instance_id:
                result["instance"] = orch.status(instance_id=instance_id)
            if args.url:
                from bookforge.runtime.health import check_http_health

                result["service"] = check_http_health(args.url)
            if not result:
                raise RuntimeError("runtime-health needs --instance-id, --url, or saved runtime state")
            result["status"] = "ok"
        elif args.command == "runtime-stop":
            instance_id = args.instance_id or runtime_state.get("instance", {}).get("instance_id")
            if not instance_id:
                raise RuntimeError("runtime-stop requires --instance-id or saved runtime state")
            orch = RuntimeOrchestrator(runtime_cfg)
            result = orch.stop(instance_id=instance_id)
        elif args.command == "runtime-destroy":
            instance_id = args.instance_id or runtime_state.get("instance", {}).get("instance_id")
            if not instance_id:
                raise RuntimeError("runtime-destroy requires --instance-id or saved runtime state")
            orch = RuntimeOrchestrator(runtime_cfg)
            result = orch.destroy(instance_id=instance_id)
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("status") in {"PASS", "WARN", "ok"} else 1)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
