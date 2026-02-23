from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS, get_preset, presets_payload
from bookforge.qc.image_qc import choose_best_variant, write_qa_report
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.review.contact_sheet import generate_contact_sheet
from bookforge.story.story_spec import build_bible_variants, parse_story
from bookforge.story.storyboard import generate_storyboard


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

    def _make_palette_tile(self, colors: List[str], out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        w, h = 1000, 180
        img = Image.new("RGB", (w, h), (246, 240, 229))
        draw = ImageDraw.Draw(img)
        block = max(1, w // max(1, len(colors)))
        for i, c in enumerate(colors):
            draw.rectangle((i * block, 0, (i + 1) * block, h), fill=c)
        img.save(out_path, "PNG")

    def preprod(self, story_path: str, out_dir: str, size: str, pages: int, variants: int) -> Dict[str, Any]:
        out = Path(out_dir)
        preprod = out / "preprod"
        (preprod / "bible_variants").mkdir(parents=True, exist_ok=True)

        parsed = parse_story(story_path, pages)
        storyboard = generate_storyboard(parsed, variants)
        (preprod / "story_parsed.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        (preprod / "storyboard.json").write_text(json.dumps(storyboard, indent=2), encoding="utf-8")
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
            p = variant["style_bible"]["palette"]
            char_prompt = f"character turnaround front and side for {variant['character_bible']['protagonist_name']}, {variant['character_bible']['wardrobe']}"
            expression_prompt = f"expression grid 4 emotions for {variant['character_bible']['protagonist_name']}"
            hands_prompt = f"hands visible, holding prop, {variant['character_bible']['protagonist_name']}"
            style_prompt = f"style frame, {variant['style_bible']['visual_mode']}, palette {', '.join(p)}"
            cover_prompt = f"front cover art concept only no text, {variant['style_bible']['visual_mode']}"
            ill.generate_option_image(char_prompt, preprod / "character_options" / f"character_turnaround_v{i}.png", (req_w, req_h), self.default_steps)
            ill.generate_option_image(expression_prompt, preprod / "character_options" / f"expression_grid_v{i}.png", (req_w, req_h), self.default_steps)
            ill.generate_option_image(hands_prompt, preprod / "character_options" / f"hands_pose_v{i}.png", (req_w, req_h), self.default_steps)
            ill.generate_option_image(style_prompt, preprod / "style_options" / f"style_frame_v{i}.png", (req_w, req_h), self.default_steps)
            self._make_palette_tile(p, preprod / "style_options" / f"palette_tile_v{i}.png")
            ill.generate_option_image(cover_prompt, preprod / "cover_options" / f"cover_concept_v{i}.png", (req_w, req_h), self.default_steps)

        option_images = sorted((preprod).rglob("*_v*.png"))
        generate_contact_sheet(option_images, preprod / "options_contact_sheet.pdf")

        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        for p in INTERIOR_LAYOUT_PRESETS:
            engine.render_interior_preview(preprod / "layout_previews" / f"interior_preview_{p.id}.pdf", size, self.bleed_in, self.safe_in, p)
        for p in COVER_LAYOUT_PRESETS:
            engine.render_cover_preview(preprod / "cover_previews" / f"cover_preview_{p.id}.pdf", trim_w, trim_h, self.bleed_in, self.safe_in, p)

        approval = {
            "approved": False,
            "approved_variant": 1,
            "approved_character": "character_turnaround_v1.png",
            "approved_style": "style_frame_v1.png",
            "approved_cover": "cover_concept_v1.png",
            "interior_layout_preset": parsed["metadata"].get("interior_layout_preset", INTERIOR_LAYOUT_PRESETS[0].id),
            "typography_preset": parsed["metadata"].get("typography_preset", TYPOGRAPHY_PRESETS[0].id),
            "cover_layout_preset": parsed["metadata"].get("cover_layout_preset", COVER_LAYOUT_PRESETS[0].id),
            "paper_thickness_in": 0.002252,
            "spine_min_in": 0.06,
            "image_steps": 6,
            "page_variants": 2,
            "fal_endpoint": "https://fal.run/fal-ai/flux/schnell",
            "spread_mode": "none",
            "spread_pages": [],
            "checkpoint_pages": 2,
            "qa_profile": "platinum",
            "max_regen_rounds": 2,
            "min_sharpness": 120.0,
            "min_entropy": 3.5,
            "min_contrast": 25.0,
            "max_border_bar_score": 0.25,
            "min_style_hist_similarity": 0.65,
            "max_page_to_page_hist_drift": 0.45,
            "notes": "",
        }
        (preprod / "APPROVAL.json").write_text(json.dumps(approval, indent=2), encoding="utf-8")
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
        storyboard_path = preprod / "storyboard.json"
        if not storyboard_path.exists():
            raise RuntimeError("Missing storyboard.json in preprod.")

        approved_character = preprod / "character_options" / approval["approved_character"]
        approved_style = preprod / "style_options" / approval["approved_style"]
        approved_cover = preprod / "cover_options" / approval["approved_cover"]
        for path in [approved_character, approved_style, approved_cover]:
            if not path.exists():
                raise RuntimeError(f"Missing approval selection: {path}")

        trim_w, trim_h = parse_trim_size(size)
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
            "locked_prompt_prefix": (vv / "prompt_prefix.txt").read_text(encoding="utf-8"),
            "locked_negative_prompt": (vv / "negative_prompt.txt").read_text(encoding="utf-8"),
            "interior_layout_preset": approval["interior_layout_preset"],
            "typography_preset": approval["typography_preset"],
            "cover_layout_preset": approval["cover_layout_preset"],
            "storyboard": json.loads(storyboard_path.read_text(encoding="utf-8")),
            "print": {"trim_size": size, "bleed_in": self.bleed_in, "safe_in": self.safe_in, "dpi": 300, "page_count": page_count, "required_pixels": required_pixels},
            "cover": {"paper_thickness_in": float(approval["paper_thickness_in"]), "spine_min_in": float(approval["spine_min_in"]), "spine_w_in": spine_w, "barcode_box_in": cover_preset["barcode_box_in"], "spine_text_min_in": 0.10},
            "fal": {"endpoint": approval.get("fal_endpoint", "https://fal.run/fal-ai/flux/schnell"), "steps": int(approval["image_steps"]), "page_variants": int(approval["page_variants"])},
            "qa": {k: approval[k] for k in ["qa_profile", "max_regen_rounds", "min_sharpness", "min_entropy", "min_contrast", "max_border_bar_score", "min_style_hist_similarity", "max_page_to_page_hist_drift"]},
            "spreads": {"mode": approval.get("spread_mode", "none"), "pages": approval.get("spread_pages", [])},
            "checkpoint": {"pages": int(approval.get("checkpoint_pages", 2))},
        }
        (out / "LOCK.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        return {"status": "PASS", "lock": str(out / "LOCK.json")}

    def _split_spread(self, spread: Path, left_out: Path, right_out: Path) -> None:
        with Image.open(spread) as im:
            w, h = im.size
            half = w // 2
            im.crop((0, 0, half, h)).save(left_out, "PNG")
            im.crop((half, 0, w, h)).save(right_out, "PNG")

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
        storyboard_pages = {p["page_number"]: p for p in lock["storyboard"].get("pages", [])}
        req_w, req_h = lock["print"]["required_pixels"]

        prompts = []
        for p in parsed["pages"]:
            sb = storyboard_pages.get(p["page_number"], {})
            sfx = f" camera:{sb.get('camera','medium')} emotion:{sb.get('emotion','warm')} setting:{sb.get('setting','storybook world')}"
            prompt = f"{lock['locked_prompt_prefix']} Scene: {p['text']}. {sfx}. {lock['locked_negative_prompt']}"
            prompts.append({"page_number": p["page_number"], "prompt": prompt})
        (out / "prompts.json").write_text(json.dumps({"prompts": prompts}, indent=2), encoding="utf-8")

        checkpoint_pages = int(lock.get("checkpoint", {}).get("pages", 0))
        check_file = out / "CHECKPOINT.json"
        if checkpoint_pages > 0 and not (check_file.exists() and json.loads(check_file.read_text(encoding="utf-8")).get("approved")):
            checkpoint_prompts = prompts[:checkpoint_pages]
            checkpoint_generated = FalFluxIllustrator(endpoint=lock["fal"]["endpoint"]).generate_page_variants(
                checkpoint_prompts,
                out / "images" / "checkpoint_variants",
                (req_w, req_h),
                1,
                Path(lock["approved_character"]),
                Path(lock["approved_style"]),
                None,
                lock["fal"]["steps"],
            )
            first_pages = [Path(checkpoint_generated["variants"][i][0]) for i in range(1, checkpoint_pages + 1)]
            cp = out / "checkpoint"
            cp.mkdir(parents=True, exist_ok=True)
            generate_contact_sheet(first_pages, cp / "first_pages_contact_sheet.pdf")
            (cp / "checkpoint_preflight.json").write_text(json.dumps({"status": "READY", "pages": checkpoint_pages}, indent=2), encoding="utf-8")
            (out / "CHECKPOINT.json").write_text(json.dumps({"approved": False, "notes": "", "overrides": {}}, indent=2), encoding="utf-8")
            return {"status": "STOPPED_CHECKPOINT", "out_dir": str(out)}

        ill = FalFluxIllustrator(endpoint=lock["fal"]["endpoint"])
        generated = ill.generate_page_variants(
            prompts,
            out / "images" / "variants",
            (req_w, req_h),
            lock["fal"]["page_variants"],
            Path(lock["approved_character"]),
            Path(lock["approved_style"]),
            Path(lock["approved_style"]).with_name(f"palette_tile_v{lock['approved_variant']}.png"),
            lock["fal"]["steps"],
        )

        selected, upscaled_pages, qa_attempts = [], [], []
        selected_dir = out / "images"
        selected_dir.mkdir(parents=True, exist_ok=True)
        prev_ref = None
        for page in parsed["pages"]:
            no = page["page_number"]
            variant_paths = [Path(p) for p in generated["variants"][no]]
            best_path, qa = choose_best_variant(variant_paths, lock["qa"], Path(lock["approved_style"]), prev_ref)
            qa_attempts.append({"page": no, "attempt": 1, **qa})
            rounds = 0
            hard_prompt = prompts[no - 1]["prompt"]
            while not qa["passes"] and rounds < lock["qa"]["max_regen_rounds"]:
                rounds += 1
                hard_prompt += " single main character only, hands fully visible, no extra characters, clean anatomy"
                regen = ill.generate_page_variants([{"page_number": no, "prompt": hard_prompt}], out / "images" / "variants", (req_w, req_h), lock["fal"]["page_variants"], Path(lock["approved_character"]), Path(lock["approved_style"]), None, lock["fal"]["steps"])
                best_path, qa = choose_best_variant([Path(p) for p in regen["variants"][no]], lock["qa"], Path(lock["approved_style"]), prev_ref)
                qa_attempts.append({"page": no, "attempt": rounds + 1, **qa})

            dst = selected_dir / f"page_{no:03d}.png"
            with Image.open(best_path) as im:
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
            prev_ref = dst

        if lock.get("spreads", {}).get("mode") == "custom" and lock.get("spreads", {}).get("pages"):
            a, b = lock["spreads"]["pages"][:2]
            spread_prompt = prompts[a - 1]["prompt"] + " panoramic double-page spread"
            spread = ill.generate_page_variants([{"page_number": a, "prompt": spread_prompt}], out / "images" / "variants", (req_w * 2, req_h), 1, Path(lock["approved_character"]), Path(lock["approved_style"]), None, lock["fal"]["steps"])
            spread_path = Path(spread["variants"][a][0])
            self._split_spread(spread_path, Path(selected[a - 1]), Path(selected[b - 1]))

        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        trim_w, trim_h = parse_trim_size(size)
        interior = out / "interior.pdf"
        cover = out / "cover_wrap.pdf"
        guides = out / "cover_guides.pdf"
        engine.render_interior(parsed["pages"], selected, interior, size, self.bleed_in, self.safe_in, get_preset(lock["interior_layout_preset"], "interior"), get_preset(lock["typography_preset"], "typography"))
        engine.render_cover_wrap(cover, guides, trim_w, trim_h, self.bleed_in, self.safe_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], parsed["title"], parsed["author"], Path(lock["approved_cover"]), Path(lock["approved_style"]), get_preset(lock["cover_layout_preset"], "cover"), lock["cover"])

        preflight = KDPPreflight().run(interior, cover, selected, trim_w, trim_h, self.bleed_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], upscaled_pages, lock["cover"], self.safe_in)
        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")

        review = out / "review"
        generate_contact_sheet([Path(p) for p in selected], review / "contact_sheet.pdf")
        write_qa_report(review / "qa_report.json", {"attempts": qa_attempts, "profile": lock["qa"]})
        if lock.get("spreads", {}).get("mode") != "none":
            generate_contact_sheet([Path(p) for p in selected], review / "spread_preview.pdf", columns=2)

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
