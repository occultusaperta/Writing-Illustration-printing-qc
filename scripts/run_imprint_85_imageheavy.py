#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd)


def main() -> int:
    fal_key = (os.getenv("FAL_KEY") or os.getenv("Fal_key") or os.getenv("fal_key") or "").strip()
    if not fal_key:
        print("No Fal key found. Set FAL_KEY (preferred), Fal_key, or fal_key, then rerun this script.")
        return 0

    if run(["bookforge", "doctor", "--strict"]) != 0:
        return 1
    if run([
        "bookforge",
        "preprod",
        "--story",
        "examples/sample_story.md",
        "--out",
        "dist/imprint85",
        "--size",
        "8.5x8.5",
        "--pages",
        "24",
        "--variants",
        "4",
        "--profile",
        "ultimate_imprint_8p5x8p5_image_heavy",
    ]) != 0:
        return 1

    print("Now open dist/imprint85/preprod/options_contact_sheet.pdf and layout previews, then edit APPROVAL.json and set approved=true, then run lock + studio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
