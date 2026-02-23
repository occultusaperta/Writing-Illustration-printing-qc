from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS, get_preset, presets_payload
from bookforge.qc.image_qc import choose_best_variant, write_qa_report
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.review.contact_sheet import generate_contact_sheet
from bookforge.story.story_spec import build_bible_variants, parse_story
from bookforge.story.storyboard import generate_storyboard



def _parse_spread_pairs(spreads: Dict[str, Any], page_count: int) -> List[Tuple[int, int]]:
    mode = spreads.get("mode", "none")
    if mode == "none":
        return []
    if mode == "every_4":
        return [(p, p + 1) for p in range(4, page_count, 4) if p + 1 <= page_count]
    if mode != "custom_pairs":
        raise RuntimeError(f"Unsupported spread mode: {mode}")

    pairs = spreads.get("pairs", [])
    if not isinstance(pairs, list):
        raise RuntimeError("Spread pairs must be a list of [left,right] page numbers.")
    parsed: List[Tuple[int, int]] = []
    used_pages: set[int] = set()
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise RuntimeError("Each spread pair must contain exactly two page numbers.")
        left, right = int(pair[0]), int(pair[1])
        if right != left + 1:
            raise RuntimeError(f"Spread pair [{left}, {right}] is not consecutive.")
        if left < 1 or right > page_count:
            raise RuntimeError(f"Spread pair [{left}, {right}] is out of page range 1..{page_count}.")
        if left in used_pages or right in used_pages:
            raise RuntimeError(f"Spread pair [{left}, {right}] overlaps another spread pair.")
        used_pages.update({left, right})
        parsed.append((left, right))
    return sorted(parsed)


def _apply_checkpoint_overrides(prompts: List[Dict[str, Any]], checkpoint_payload: Dict[str, Any] | None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    payload = checkpoint_payload or {}
    overrides = payload.get("overrides") if payload.get("approved") else {}
    if not isinstance(overrides, dict):
        overrides = {}

    addendum_raw = overrides.get("page_prompt_addendum", {})
    addendum_map = {int(k): str(v) for k, v in addendum_raw.items()} if isinstance(addendum_raw, dict) else {}
    force_regen_raw = overrides.get("force_regen", [])
    force_regen = sorted({int(p) for p in force_regen_raw}) if isinstance(force_regen_raw, list) else []
    pref_raw = overrides.get("variant_preference", {})
    variant_pref = {int(k): int(v) for k, v in pref_raw.items()} if isinstance(pref_raw, dict) else {}

    merged = []
    for item in prompts:
        page_no = int(item["page_number"])
        prompt = item["prompt"]
        if page_no in addendum_map:
            prompt = f"{prompt} {addendum_map[page_no]}".strip()
        merged.append({"page_number": page_no, "prompt": prompt})

    return merged, {
        "approved": bool(payload.get("approved", False)),
        "notes": str(payload.get("notes", "")),
        "page_prompt_addendum": {str(k): v for k, v in sorted(addendum_map.items())},
        "force_regen": force_regen,
        "variant_preference": {str(k): v for k, v in sorted(variant_pref.items())},
    }


def _order_variants(variant_paths: List[Path], preferred_variant: int | None) -> List[Path]:
    if not preferred_variant:
        return variant_paths
    preferred_token = f"_v{preferred_variant}.png"
    preferred = [p for p in variant_paths if p.name.endswith(preferred_token)]
    others = [p for p in variant_paths if p not in preferred]
    return preferred + others


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
            "spread_pairs": [],
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
            "spreads": {
                "mode": approval.get("spread_mode", "none"),
                "pairs": approval.get("spread_pairs", []),
            },
            "checkpoint": {"pages": int(approval.get("checkpoint_pages", 2))},
        }
        if not lock["spreads"]["pairs"] and approval.get("spread_pages"):
            pages = approval.get("spread_pages", [])
            if isinstance(pages, list) and len(pages) >= 2:
                lock["spreads"]["mode"] = "custom_pairs"
                lock["spreads"]["pairs"] = [[int(pages[0]), int(pages[1])]]

        _parse_spread_pairs(lock["spreads"], page_count)
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

        checkpoint_payload = json.loads(check_file.read_text(encoding="utf-8")) if check_file.exists() else {}
        prompts, checkpoint_summary = _apply_checkpoint_overrides(prompts, checkpoint_payload)
        (out / "prompts.json").write_text(json.dumps({"prompts": prompts, "checkpoint": checkpoint_summary}, indent=2), encoding="utf-8")

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
        force_regen_set = {int(p) for p in checkpoint_summary.get("force_regen", [])}
        variant_pref = {int(k): int(v) for k, v in checkpoint_summary.get("variant_preference", {}).items()}

        for page in parsed["pages"]:
            no = page["page_number"]
            variant_paths = _order_variants([Path(p) for p in generated["variants"][no]], variant_pref.get(no))
            best_path, qa = choose_best_variant(variant_paths, lock["qa"], Path(lock["approved_style"]), prev_ref)
            qa_attempts.append({"page": no, "attempt": 1, **qa})
            rounds = 0
            hard_prompt = prompts[no - 1]["prompt"]
            needs_forced_regen = no in force_regen_set
            while ((not qa["passes"]) or needs_forced_regen) and rounds < lock["qa"]["max_regen_rounds"]:
                rounds += 1
                needs_forced_regen = False
                hard_prompt += " single main character only, hands fully visible, no extra characters, clean anatomy"
                regen = ill.generate_page_variants([{"page_number": no, "prompt": hard_prompt}], out / "images" / "variants", (req_w, req_h), lock["fal"]["page_variants"], Path(lock["approved_character"]), Path(lock["approved_style"]), None, lock["fal"]["steps"])
                regen_variants = _order_variants([Path(p) for p in regen["variants"][no]], variant_pref.get(no))
                best_path, qa = choose_best_variant(regen_variants, lock["qa"], Path(lock["approved_style"]), prev_ref)
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

        spread_pairs = _parse_spread_pairs(lock.get("spreads", {}), len(parsed["pages"]))
        for a, b in spread_pairs:
            spread_prompt = prompts[a - 1]["prompt"] + " panoramic double-page spread"
            spread_ok = False
            spread_round = 0
            spread_path: Path | None = None
            while not spread_ok and spread_round <= lock["qa"]["max_regen_rounds"]:
                spread_round += 1
                spread = ill.generate_page_variants([{"page_number": a, "prompt": spread_prompt}], out / "images" / "variants", (req_w * 2, req_h), 1, Path(lock["approved_character"]), Path(lock["approved_style"]), None, lock["fal"]["steps"])
                spread_path = Path(spread["variants"][a][0])
                _, spread_qa = choose_best_variant([spread_path], lock["qa"], Path(lock["approved_style"]), None)
                qa_attempts.append({"page": f"{a}-{b}", "attempt": spread_round, "spread": True, **spread_qa})
                if not spread_qa["passes"]:
                    continue
                self._split_spread(spread_path, Path(selected[a - 1]), Path(selected[b - 1]))
                left_best, left_qa = choose_best_variant([Path(selected[a - 1])], lock["qa"], Path(lock["approved_style"]), Path(selected[a - 2]) if a > 1 else None)
                right_best, right_qa = choose_best_variant([Path(selected[b - 1])], lock["qa"], Path(lock["approved_style"]), Path(selected[a - 1]))
                qa_attempts.append({"page": a, "attempt": spread_round, "spread_half": "left", **left_qa})
                qa_attempts.append({"page": b, "attempt": spread_round, "spread_half": "right", **right_qa})
                spread_ok = bool(left_qa["passes"] and right_qa["passes"])
            if not spread_ok:
                raise RuntimeError(f"Spread QA failed for pair [{a}, {b}] after regeneration rounds.")

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
        write_qa_report(review / "qa_report.json", {"attempts": qa_attempts, "profile": lock["qa"], "checkpoint_overrides_applied": checkpoint_summary})
        if spread_pairs:
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
