from __future__ import annotations

import argparse
import json
import sys

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

    lock = sub.add_parser("lock", help="Freeze approved character and style")
    lock.add_argument("--out", required=True)
    lock.add_argument("--size", default="8.5x8.5")
    lock.add_argument("--pages", type=int, default=24)

    studio = sub.add_parser("studio", help="Generate full package after lock")
    studio.add_argument("--story", required=True)
    studio.add_argument("--out", required=True)
    studio.add_argument("--size", default="8.5x8.5")
    studio.add_argument("--pages", type=int, default=24)
    studio.add_argument("--illustrator", choices=["auto", "fal", "openai"], default="fal")
    studio.add_argument("--require-lock", action="store_true")

    args = parser.parse_args()
    pipeline = BookforgePipeline()

    try:
        if args.command == "doctor":
            result = pipeline.doctor(strict=args.strict)
        elif args.command == "preprod":
            result = pipeline.preprod(args.story, args.out, args.size, args.pages, args.variants)
        elif args.command == "lock":
            result = pipeline.lock(args.out, args.size, args.pages)
        elif args.command == "studio":
            result = pipeline.studio(args.story, args.out, args.size, args.pages, args.illustrator, args.require_lock)
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
