from __future__ import annotations

import argparse
import json
import sys

from bookforge.pipeline import BookforgePipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="BookForge pipeline CLI")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="Validate pipeline setup and knowledge files")
    doctor.add_argument("--strict", action="store_true")

    run = sub.add_parser("run", help="Run full book pipeline")
    run.add_argument("--idea", required=True)
    run.add_argument("--pages", type=int, default=24)
    run.add_argument("--size", default="8.5x8.5")
    run.add_argument("--out", required=True)
    run.add_argument("--stop-after", choices=["style"], default=None)
    run.add_argument("--writer", choices=["full-pipeline", "template"], default="full-pipeline")
    run.add_argument("--illustrator", choices=["auto", "fal", "openai", "placeholder"], default="auto")
    run.add_argument("--allow-placeholder", action="store_true")

    args = parser.parse_args()
    pipeline = BookforgePipeline()

    if args.command == "doctor":
        result = pipeline.doctor(strict=args.strict)
        print(result["status"])
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "PASS" else 1)

    if args.command == "run":
        result = pipeline.run(idea=args.idea, pages=args.pages, size=args.size, out_dir=args.out, stop_after=args.stop_after, writer=args.writer, illustrator=args.illustrator, allow_placeholder=args.allow_placeholder)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("status") in {"PASS", "WARN", "STOPPED_AFTER_STYLE"} else 1)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
