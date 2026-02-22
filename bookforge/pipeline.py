from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS, get_preset, presets_payload
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.story.story_spec import build_bible_variants, parse_story


class BookforgePipeline:
    def __init__(self) -> None:
        self.bleed_in = 0.125
        self.safe_in = 0.375
        self.default_steps = 6
        self.default_page_variants = 2

    def doctor(self, strict: bool = False) -> Dict[str, Any]:
        import os

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
        (preprod / "bible_variants").mkdir(parents=True, exist_ok=True)

        parsed = parse_story(story_path, pages)
        (preprod / "story_parsed.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        bible_variants = build_bible_variants(parsed, variants=variants)

        for variant in bible_variants:
            folder = preprod / "bible_variants" / f"v{variant['variant']}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "character_bible.json").write_text(json.dumps(variant["character_bible"], indent=2), encoding="utf-8")
            (folder / "style_bible.json").write_text(json.dumps(variant["style_bible"], indent=2), encoding="utf-8")
            (folder / "prompt_prefix.txt").write_text(variant["locked_prompt_prefix"], encoding="utf-8")
            (folder / "negative_prompt.txt").write_text(variant["locked_negative_prompt"], encoding="utf-8")

        (preprod / "layout_options.json").write_text(json.dumps(presets_payload(), indent=2), encoding="utf-8")

        trim_w, trim_h = parse_trim_size(size)
        req_w = int((trim_w + 2 * self.bleed_in) * 300)
        req_h = int((trim_h + 2 * self.bleed_in) * 300)

        ill = FalFluxIllustrator()
        for variant in bible_variants:
            i = variant["variant"]
            char_prompt = f"character turnaround for {variant['character_bible']['protagonist_name']}, {variant['character_bible']['wardrobe']}, consistent design"
            style_prompt = f"style frame, {variant['style_bible']['visual_mode']}, palette {', '.join(variant['style_bible']['palette'])}"
            cover_prompt = f"front cover art concept only no text, {variant['style_bible']['visual_mode']}, protagonist {variant['character_bible']['protagonist_name']}"
            ill.generate_option_image(char_prompt, preprod / "character_options" / f"char_v{i}.png", (req_w, req_h), self.default_steps)
            ill.generate_option_image(style_prompt, preprod / "style_options" / f"style_v{i}.png", (req_w, req_h), self.default_steps)
            ill.generate_option_image(cover_prompt, preprod / "cover_options" / f"cover_v{i}.png", (req_w, req_h), self.default_steps)

        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        for p in INTERIOR_LAYOUT_PRESETS:
            engine.render_interior_preview(preprod / "layout_previews" / f"interior_preview_{p.id}.pdf", size, self.bleed_in, self.safe_in, p)
        for p in COVER_LAYOUT_PRESETS:
            engine.render_cover_preview(preprod / "cover_previews" / f"cover_preview_{p.id}.pdf", trim_w, trim_h, self.bleed_in, self.safe_in, p)

        approval = {
            "approved": False,
            "approved_variant": 1,
            "approved_character": "char_v1.png",
            "approved_style": "style_v1.png",
            "approved_cover": "cover_v1.png",
            "interior_layout_preset": parsed["metadata"].get("interior_layout_preset", INTERIOR_LAYOUT_PRESETS[0].id),
            "typography_preset": parsed["metadata"].get("typography_preset", TYPOGRAPHY_PRESETS[0].id),
            "cover_layout_preset": parsed["metadata"].get("cover_layout_preset", COVER_LAYOUT_PRESETS[0].id),
            "paper_thickness_in": 0.002252,
            "spine_min_in": 0.06,
            "image_steps": 6,
            "page_variants": 2,
            "notes": "",
        }
        (preprod / "APPROVAL.json").write_text(json.dumps(approval, indent=2), encoding="utf-8")
        (preprod / "APPROVAL_INSTRUCTIONS.md").write_text(
            "1) Pick approved_variant and matching char/style/cover image files.\n2) Pick interior/typography/cover presets.\n3) Set approved=true.\n4) Run bookforge lock --out <dir>.\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "stage": "preprod", "out_dir": str(out)}

    def lock(self, out_dir: str, size: str = "8.5x8.5", page_count: int = 24) -> Dict[str, Any]:
        out = Path(out_dir)
        preprod = out / "preprod"
        approval = json.loads((preprod / "APPROVAL.json").read_text(encoding="utf-8"))
        if not approval.get("approved"):
            raise RuntimeError("Approval incomplete. Set approved=true in APPROVAL.json.")

        variant = int(approval["approved_variant"])
        vv = preprod / "bible_variants" / f"v{variant}"
        if not vv.exists():
            raise RuntimeError(f"Missing chosen bible variant folder: {vv}")

        approved_character = (preprod / "character_options" / approval["approved_character"]).resolve()
        approved_style = (preprod / "style_options" / approval["approved_style"]).resolve()
        approved_cover = (preprod / "cover_options" / approval["approved_cover"]).resolve()
        for p in [approved_character, approved_style, approved_cover]:
            if not p.exists():
                raise RuntimeError(f"Approved file missing: {p}")

        trim_w, trim_h = parse_trim_size(size)
        page_count = int(page_count)
        required_pixels = [int((trim_w + 2 * self.bleed_in) * 300), int((trim_h + 2 * self.bleed_in) * 300)]
        spine_w = max(float(approval["spine_min_in"]), page_count * float(approval["paper_thickness_in"]))
        cover_preset = get_preset(approval["cover_layout_preset"], "cover")

        lock = {
            "approved_variant": variant,
            "approved_character": str(approved_character),
            "approved_style": str(approved_style),
            "approved_cover": str(approved_cover),
            "character_bible": json.loads((vv / "character_bible.json").read_text(encoding="utf-8")),
            "style_bible": json.loads((vv / "style_bible.json").read_text(encoding="utf-8")),
            "interior_layout_preset": approval["interior_layout_preset"],
            "typography_preset": approval["typography_preset"],
            "cover_layout_preset": approval["cover_layout_preset"],
            "locked_prompt_prefix": (vv / "prompt_prefix.txt").read_text(encoding="utf-8"),
            "locked_negative_prompt": (vv / "negative_prompt.txt").read_text(encoding="utf-8"),
            "print": {"trim_size": size, "bleed_in": self.bleed_in, "safe_in": self.safe_in, "dpi": 300, "page_count": page_count, "required_pixels": required_pixels},
            "cover": {
                "paper_thickness_in": float(approval["paper_thickness_in"]),
                "spine_min_in": float(approval["spine_min_in"]),
                "spine_w_in": spine_w,
                "barcode_box_in": cover_preset["barcode_box_in"],
                "spine_text_min_in": 0.10,
            },
            "fal": {"endpoint": "https://fal.run/fal-ai/flux/schnell", "steps": int(approval["image_steps"]), "page_variants": int(approval["page_variants"])},
        }
        get_preset(lock["interior_layout_preset"], "interior")
        get_preset(lock["typography_preset"], "typography")
        (out / "LOCK.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        return {"status": "PASS", "lock": str(out / "LOCK.json")}

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

        parsed = parse_story(story_path, pages)
        trim_w, trim_h = parse_trim_size(size)
        req_w, req_h = lock["print"]["required_pixels"]

        prompts = []
        for p in parsed["pages"]:
            scene = p["text"]
            prompt = f"{lock['locked_prompt_prefix']} Scene: {scene}. Safety: subject inside safe area; avoid faces near trim. {lock['locked_negative_prompt']}"
            prompts.append({"page_number": p["page_number"], "prompt": prompt})
        (out / "prompts.json").write_text(json.dumps({"prompts": prompts}, indent=2), encoding="utf-8")

        ill = FalFluxIllustrator(endpoint=lock["fal"]["endpoint"])
        generated = ill.generate_page_variants(prompts, out / "images" / "variants", (req_w, req_h), lock["fal"]["page_variants"], Path(lock["approved_character"]), lock["fal"]["steps"])

        overrides = json.loads((out / "OVERRIDES.json").read_text(encoding="utf-8")) if (out / "OVERRIDES.json").exists() else {}
        selected, upscaled_pages = [], []
        selected_dir = out / "images"
        selected_dir.mkdir(parents=True, exist_ok=True)
        for page in parsed["pages"]:
            no = page["page_number"]
            choices = generated["variants"][no]
            requested = max(1, int(overrides.get(str(no), 1))) - 1
            candidate_order = list(range(requested, len(choices))) + list(range(0, requested))
            src = None
            for idx in candidate_order:
                c = Path(choices[idx])
                try:
                    with Image.open(c) as im:
                        if im.width > 0 and im.height > 0:
                            src = c
                            break
                except Exception:
                    continue
            if src is None:
                raise RuntimeError(f"No valid image variant for page {no}")
            dst = selected_dir / f"page_{no:03d}.png"
            with Image.open(src) as im:
                work = im.convert("RGB")
                if work.width < req_w or work.height < req_h:
                    scale = max(req_w / work.width, req_h / work.height)
                    work = work.resize((math.ceil(work.width * scale), math.ceil(work.height * scale)), Image.Resampling.LANCZOS)
                    upscaled_pages.append(no)
                if work.width != req_w or work.height != req_h:
                    left = (work.width - req_w) // 2
                    top = (work.height - req_h) // 2
                    work = work.crop((left, top, left + req_w, top + req_h))
                work.save(dst, "PNG")
            selected.append(str(dst))

        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        interior = out / "interior.pdf"
        cover = out / "cover_wrap.pdf"
        guides = out / "cover_guides.pdf"
        engine.render_interior(parsed["pages"], selected, interior, size, self.bleed_in, self.safe_in, get_preset(lock["interior_layout_preset"], "interior"), get_preset(lock["typography_preset"], "typography"))
        engine.render_cover_wrap(cover, guides, trim_w, trim_h, self.bleed_in, self.safe_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], parsed["title"], parsed["author"], Path(lock["approved_cover"]), Path(lock["approved_style"]), get_preset(lock["cover_layout_preset"], "cover"), lock["cover"])        

        preflight = KDPPreflight().run(interior, cover, selected, trim_w, trim_h, self.bleed_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], upscaled_pages, lock["cover"], self.safe_in)
        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")

        zip_path = out / "bookforge_package.zip"
        self._create_package(zip_path, out)
        return {"status": preflight["status"], "out_dir": str(out), "zip": str(zip_path)}

    def _create_package(self, zip_path: Path, out: Path) -> None:
        include = ["interior.pdf", "cover_wrap.pdf", "cover_guides.pdf", "preflight_report.json", "LOCK.json", "prompts.json"]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in include:
                path = out / rel
                if path.exists():
                    zf.write(path, arcname=rel)
            for p in (out / "images").rglob("*.png"):
                zf.write(p, arcname=str(p.relative_to(out)))
