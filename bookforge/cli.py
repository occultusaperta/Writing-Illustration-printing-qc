from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from bookforge.pipeline import BookforgePipeline


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

    args = parser.parse_args()
    pipeline = BookforgePipeline()

    try:
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
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("status") in {"PASS", "WARN"} else 1)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
