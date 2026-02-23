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
    fal_key = (os.getenv("FAL_KEY") or os.getenv("Fal_key") or os.getenv("fal_key") or "").strip()
    if not fal_key:
        print("FAL_KEY/Fal_key/fal_key not set; skipping smoke run.")
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
        OUT_DIR / "review" / "quality_summary.md",
        OUT_DIR / "review" / "report.html",
        OUT_DIR / "review" / "thumbs",
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
    if "cache_keys" not in qa_report:
        print("Smoke run failed; qa_report missing cache_keys")
        return 1
    first_attempt = qa_report.get("attempts", [{}])[0].get("best", {}) if qa_report.get("attempts") else {}
    required_integrity = {"text_likelihood", "watermark_likelihood", "logo_likelihood", "border_artifact_score", "brightness_mean", "out_of_gamut_risk"}
    if first_attempt and not required_integrity.issubset(set(first_attempt.keys())):
        print("Smoke run failed; integrity metrics missing from qa_report")
        return 1

    if not (OUT_DIR / "images" / "variants_raw").exists():
        print("Smoke run failed; variants_raw missing")
        return 1

    production = json.loads((OUT_DIR / "review" / "production_report.json").read_text(encoding="utf-8"))
    if "post" not in production:
        print("Smoke run failed; production_report missing post fields")
        return 1
    for key in ["crop_mode", "director_grade_enabled", "tone_curve_preset"]:
        if key not in production.get("post", {}):
            print(f"Smoke run failed; production_report post missing {key}")
            return 1

    summary_text = (OUT_DIR / "review" / "quality_summary.md").read_text(encoding="utf-8")
    for section in ["Top Drift Pages", "Cache Hit Rate"]:
        if section not in summary_text:
            print(f"Smoke run failed; quality summary missing section {section}")
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
