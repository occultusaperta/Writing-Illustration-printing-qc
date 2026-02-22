from __future__ import annotations

import json
import math
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.qc.kdp_preflight import KDPPreflight


class BookforgePipeline:
    def __init__(self) -> None:
        self.bleed_in = 0.125
        self.safe_in = 0.375
        self.default_steps = 4
        self.default_page_variants = 2

    def doctor(self, strict: bool = False) -> Dict[str, Any]:
        fal = bool(os.getenv("FAL_KEY", "").strip())
        issues: List[str] = []
        if not fal:
            issues.append("FAL_KEY missing")
        if strict and issues:
            return {"status": "FAIL", "issues": issues}
        return {"status": "PASS" if fal else "WARN", "issues": issues, "provider": "fal-flux-only"}

    def preprod(self, story_path: str, out_dir: str, size: str, pages: int, variants: int) -> Dict[str, Any]:
        out = Path(out_dir)
        preprod = out / "preprod"
        preprod.mkdir(parents=True, exist_ok=True)

        parsed = self._parse_story(Path(story_path), pages)
        (preprod / "story_parsed.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")

        character_bible = {
            "protagonist_name": parsed["title"].split()[0] if parsed["title"] else "Protagonist",
            "age": "child",
            "physical_features": {"skin": "warm tan", "hair": "short black curls", "eyes": "brown", "face": "round cheeks"},
            "wardrobe": "mustard hoodie, denim shorts, white sneakers",
            "signature_props": ["small satchel"],
            "expressions_set": ["happy", "worried", "brave", "curious"],
            "do_not_change": ["same face proportions", "same wardrobe palette", "no age drift"],
        }
        style_bible = {
            "visual_mode": "cinematic storybook gouache",
            "palette": ["#F2C14E", "#3A506B", "#5BC0BE", "#FFFFFF"],
            "lighting_rules": "soft afternoon bounce light",
            "line_texture_rules": "painterly brush texture with clean silhouettes",
            "composition_rules": "medium shots, centered protagonist, subject in safe area",
            "negative_rules": "NO text, NO watermark, NO extra limbs, NO deformed hands",
        }
        (preprod / "character_bible.json").write_text(json.dumps(character_bible, indent=2), encoding="utf-8")
        (preprod / "style_bible.json").write_text(json.dumps(style_bible, indent=2), encoding="utf-8")

        char_prompts = {
            "variants": [
                {"variant": i, "prompt": f"character sheet, front side and 3 expressions, {character_bible['wardrobe']}, children's premium illustration, variant {i}"}
                for i in range(1, variants + 1)
            ]
        }
        style_prompts = {
            "variants": [
                {"variant": i, "prompt": f"style frame environment shot for {parsed['title']}, {style_bible['visual_mode']}, palette {', '.join(style_bible['palette'])}, variant {i}"}
                for i in range(1, variants + 1)
            ]
        }
        (preprod / "character_sheet_prompts.json").write_text(json.dumps(char_prompts, indent=2), encoding="utf-8")
        (preprod / "style_frame_prompts.json").write_text(json.dumps(style_prompts, indent=2), encoding="utf-8")

        trim_w, trim_h = parse_trim_size(size)
        req_w = int((trim_w + 2 * self.bleed_in) * 300)
        req_h = int((trim_h + 2 * self.bleed_in) * 300)
        ill = FalFluxIllustrator()
        for item in char_prompts["variants"]:
            ill.generate_option_image(item["prompt"], preprod / "character_options" / f"char_v{item['variant']}.png", (req_w, req_h), self.default_steps)
        for item in style_prompts["variants"]:
            ill.generate_option_image(item["prompt"], preprod / "style_options" / f"style_v{item['variant']}.png", (req_w, req_h), self.default_steps)

        approval = {"approved": False, "approved_character": "char_v?.png", "approved_style": "style_v?.png", "notes": ""}
        (preprod / "APPROVAL.json").write_text(json.dumps(approval, indent=2), encoding="utf-8")
        (preprod / "APPROVAL_INSTRUCTIONS.md").write_text(
            f"Open the options, pick 1 character + 1 style, edit APPROVAL.json, then run: bookforge lock --out {out_dir}\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "stage": "preprod", "out_dir": str(out)}

    def lock(self, out_dir: str, size: str = "8.5x8.5", page_count: int = 24) -> Dict[str, Any]:
        out = Path(out_dir)
        preprod = out / "preprod"
        approval_path = preprod / "APPROVAL.json"
        if not approval_path.exists():
            raise RuntimeError("Missing preprod/APPROVAL.json. Run bookforge preprod first.")
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        if not approval.get("approved") or "?" in approval.get("approved_character", "") or "?" in approval.get("approved_style", ""):
            raise RuntimeError("Approval incomplete. Set approved=true and choose approved_character/style in APPROVAL.json.")

        trim_w, trim_h = parse_trim_size(size)
        lock = {
            "approved_character": str(preprod / "character_options" / approval["approved_character"]),
            "approved_style": str(preprod / "style_options" / approval["approved_style"]),
            "character_bible": json.loads((preprod / "character_bible.json").read_text(encoding="utf-8")),
            "style_bible": json.loads((preprod / "style_bible.json").read_text(encoding="utf-8")),
            "locked_prompt_prefix": "premium children's book illustration, keep protagonist consistent with approved character sheet and approved style frame",
            "locked_negative_prompt": "text, watermark, logo, extra limbs, malformed hands, cropped face, low quality",
            "config": {
                "trim": size,
                "bleed": self.bleed_in,
                "safe": self.safe_in,
                "dpi": 300,
                "fal_endpoint": "https://fal.run/fal-ai/flux/schnell",
                "steps": self.default_steps,
                "variants": self.default_page_variants,
                "page_count": page_count,
                "required_pixels": [int((trim_w + 2 * self.bleed_in) * 300), int((trim_h + 2 * self.bleed_in) * 300)],
            },
        }
        (out / "LOCK.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        return {"status": "PASS", "lock": str(out / 'LOCK.json')}

    def studio(self, story_path: str, out_dir: str, size: str, pages: int, illustrator: str, require_lock: bool) -> Dict[str, Any]:
        if illustrator == "openai":
            raise RuntimeError("OpenAI image provider disabled; Fal/Flux only.")
        if illustrator not in {"fal", "auto"}:
            raise RuntimeError("Only Fal/Flux is supported for studio generation.")

        out = Path(out_dir)
        lock_path = out / "LOCK.json"
        if require_lock and not lock_path.exists():
            raise RuntimeError("LOCK.json missing. Run preprod + lock before studio.")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))

        trim_w, trim_h = parse_trim_size(size)
        req_w = int((trim_w + 2 * self.bleed_in) * 300)
        req_h = int((trim_h + 2 * self.bleed_in) * 300)

        parsed = self._parse_story(Path(story_path), pages)
        page_plan = {"title": parsed["title"], "author": parsed["author"], "pages": parsed["pages"]}
        (out / "page_plan.json").write_text(json.dumps(page_plan, indent=2), encoding="utf-8")

        prompts = []
        for p in parsed["pages"]:
            scene = p["text"]
            final_prompt = f"{lock['locked_prompt_prefix']}. Scene: {scene}. Composition: keep key subject inside safe area while background extends to bleed. Negative prompt: {lock['locked_negative_prompt']}"
            prompts.append({"page_number": p["page_number"], "prompt": final_prompt})
        (out / "prompts.json").write_text(json.dumps({"prompts": prompts}, indent=2), encoding="utf-8")

        ill = FalFluxIllustrator(endpoint=lock["config"]["fal_endpoint"])
        variants_out = out / "images" / "variants"
        generated = ill.generate_page_variants(
            prompts,
            variants_out,
            (req_w, req_h),
            variants=lock["config"].get("variants", self.default_page_variants),
            reference_image=Path(lock["approved_character"]),
            steps=lock["config"].get("steps", self.default_steps),
        )

        overrides_path = out / "OVERRIDES.json"
        overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else {}
        selected_dir = out / "images"
        selected_dir.mkdir(parents=True, exist_ok=True)
        selected: List[str] = []
        upscaled_pages: List[int] = []

        for page in parsed["pages"]:
            no = page["page_number"]
            variant_idx = int(overrides.get(str(no), 1))
            src = Path(generated["variants"][no][variant_idx - 1])
            dst = selected_dir / f"page_{no:03d}.png"
            with Image.open(src) as im:
                work = im.convert("RGB")
                if work.width < req_w or work.height < req_h:
                    work = work.resize((max(req_w, work.width), max(req_h, work.height)), Image.Resampling.LANCZOS)
                    upscaled_pages.append(no)
                if work.width != req_w or work.height != req_h:
                    left = max(0, (work.width - req_w) // 2)
                    top = max(0, (work.height - req_h) // 2)
                    work = work.crop((left, top, left + req_w, top + req_h))
                work.save(dst, format="PNG")
            selected.append(str(dst))

        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        interior = out / "interior.pdf"
        cover = out / "cover_wrap.pdf"
        guides = out / "cover_guides.pdf"
        engine.render_interior(parsed["pages"], selected, interior, size, self.bleed_in, self.safe_in)
        page_count = len(parsed["pages"])
        paper_thickness = 0.002252
        spine_w = max(0.06, page_count * paper_thickness)
        engine.render_cover_wrap(cover, guides, trim_w, trim_h, self.bleed_in, self.safe_in, page_count, spine_w)

        preflight = KDPPreflight().run(interior, cover, selected, trim_w, trim_h, self.bleed_in, page_count, spine_w, upscaled_pages)
        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")

        zip_path = out / "bookforge_package.zip"
        self._create_package(zip_path, out)
        return {"status": preflight["status"], "out_dir": str(out), "zip": str(zip_path)}

    def _create_package(self, zip_path: Path, out: Path) -> None:
        include = ["interior.pdf", "cover_wrap.pdf", "cover_guides.pdf", "preflight_report.json", "LOCK.json", "page_plan.json", "prompts.json"]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in include:
                path = out / rel
                if path.exists():
                    zf.write(path, arcname=rel)
            for p in (out / "images").rglob("*.png"):
                zf.write(p, arcname=str(p.relative_to(out)))

    def _parse_story(self, story_path: Path, pages: int) -> Dict[str, Any]:
        text = story_path.read_text(encoding="utf-8")
        title = story_path.stem.replace("_", " ").title()
        author = "Internal Studio"

        chunks = re.split(r"(?:^|\n)#{1,6}\s*Page\s*\d+[:\-]?", text, flags=re.IGNORECASE)
        parts = [c.strip() for c in chunks if c.strip()]
        if len(parts) < 2:
            parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not parts:
            raise RuntimeError("Story file is empty.")

        per_page: List[str] = []
        idx = 0
        for p in range(pages):
            take = max(1, math.ceil((len(parts) - idx) / max(1, pages - p)))
            per_page.append(" ".join(parts[idx: idx + take]))
            idx += take
            if idx >= len(parts):
                idx = len(parts)
        pages_payload = [{"page_number": i + 1, "text": per_page[i]} for i in range(pages)]
        return {"title": title, "author": author, "pages": pages_payload}
