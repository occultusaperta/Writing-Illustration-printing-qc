#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "dist" / "smoke"
PREPROD_APPROVAL = OUT_DIR / "preprod" / "APPROVAL.json"


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    if not os.getenv("FAL_KEY", "").strip():
        print("FAL_KEY not set; skipping smoke run.")
        return 0

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    run(["bookforge", "doctor", "--strict"])
    run(["bookforge", "preprod", "--story", "examples/sample_story.md", "--out", str(OUT_DIR), "--size", "8.5x8.5", "--pages", "8", "--variants", "2"])

    approval = json.loads(PREPROD_APPROVAL.read_text(encoding="utf-8"))
    variant = 1
    approval["approved"] = True
    approval["approved_variant"] = variant
    approval["approved_character"] = f"character_turnaround_v{variant}.png"
    approval["approved_style"] = f"style_frame_v{variant}.png"
    approval["approved_cover"] = f"cover_concept_v{variant}.png"
    approval["checkpoint_pages"] = 0
    approval["qa_profile"] = "platinum"
    approval["spread_mode"] = "custom_pairs"
    approval["spread_pairs"] = [[2, 3]]
    approval["fal_endpoint"] = approval.get("fal_endpoint", "https://fal.run/fal-ai/flux/schnell")
    PREPROD_APPROVAL.write_text(json.dumps(approval, indent=2), encoding="utf-8")

    run(["bookforge", "lock", "--out", str(OUT_DIR), "--size", "8.5x8.5", "--pages", "8"])
    (OUT_DIR / "CHECKPOINT.json").write_text(
        json.dumps(
            {
                "approved": True,
                "notes": "smoke override",
                "overrides": {
                    "page_prompt_addendum": {"3": "make it brighter"},
                    "force_regen": [5],
                    "variant_preference": {"7": 2},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    run(["bookforge", "studio", "--story", "examples/sample_story.md", "--out", str(OUT_DIR), "--size", "8.5x8.5", "--pages", "8", "--illustrator", "fal", "--require-lock"])

    expected = [
        OUT_DIR / "interior.pdf",
        OUT_DIR / "cover_wrap.pdf",
        OUT_DIR / "cover_guides.pdf",
        OUT_DIR / "preflight_report.json",
        OUT_DIR / "LOCK.json",
        OUT_DIR / "prompts.json",
        OUT_DIR / "bookforge_package.zip",
        OUT_DIR / "review" / "contact_sheet.pdf",
        OUT_DIR / "review" / "qa_report.json",
        OUT_DIR / "review" / "proof_pack.pdf",
        OUT_DIR / "review" / "production_report.json",
    ]
    missing = [str(p) for p in expected if not p.exists()]
    if missing:
        print("Smoke run failed; missing outputs:")
        for m in missing:
            print(f"- {m}")
        return 1

    preflight = json.loads((OUT_DIR / "preflight_report.json").read_text(encoding="utf-8"))
    if preflight.get("status") == "FAIL":
        print("Smoke run failed: preflight status is FAIL")
        return 1

    qa_report = json.loads((OUT_DIR / "review" / "qa_report.json").read_text(encoding="utf-8"))
    if "cache_hits" not in qa_report:
        print("Smoke run failed; qa_report missing cache_hits")
        return 1
    first_attempt = qa_report.get("attempts", [{}])[0].get("best", {}) if qa_report.get("attempts") else {}
    required_integrity = {"text_likelihood", "watermark_likelihood", "logo_likelihood", "border_artifact_score"}
    if first_attempt and not required_integrity.issubset(set(first_attempt.keys())):
        print("Smoke run failed; integrity metrics missing from qa_report")
        return 1

    if approval.get("spread_mode", "none") != "none":
        spread_preview = OUT_DIR / "review" / "spread_preview.pdf"
        if not spread_preview.exists():
            print("Smoke run failed; spread preview missing for spread-enabled config")
            return 1

    print("Smoke run complete:")
    print(f"- out: {OUT_DIR}")
    print(f"- preflight status: {preflight.get('status')}")
    print(f"- package: {OUT_DIR / 'bookforge_package.zip'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
