from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw

from bookforge.illustration.color_grade import add_sharpen_and_grain, grade_image
from bookforge.illustration.director_grade import apply_director_grade
from bookforge.illustration.luxury_finish import apply_canvas_grain, apply_microtexture_enhancement, apply_paint_variance
from bookforge.illustration.upscale import upscale_image
from bookforge.illustration.providers import OPENAI_DISABLED_MESSAGE, resolve_image_provider
from bookforge.illustration.prompt_contract import build_prompt_contract
from bookforge.illustration.visual_lock import ensure_reference_paths_exist, normalize_visual_lock, validate_visual_lock
from bookforge.illustration.smart_crop import smart_crop_to_target
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.layout.presets import COVER_LAYOUT_PRESETS, INTERIOR_LAYOUT_PRESETS, TYPOGRAPHY_PRESETS, get_preset, presets_payload
from bookforge.editorial.dual_address import analyze_dual_address
from bookforge.editorial.eye_flow import verify_focus_not_covered_by_panel
from bookforge.editorial.hidden_artifacts import apply_artifact_plan_to_pages, propose_artifact_options
from bookforge.editorial.hook_packaging import generate_hook_pack
from bookforge.editorial.page_turns import build_page_turn_map
from bookforge.editorial.readaloud_script import generate_readaloud_script
from bookforge.editorial.report import render_editorial_report_md
from bookforge.editorial.rhythm_audit import audit_rhythm_and_rhyme
from bookforge.editorial.trade_dress import generate_trade_dress
from bookforge.color_script import plan_color_script, write_planning_artifacts as write_color_planning_artifacts
from bookforge.color_script.prompting import build_color_negative_lines, build_color_prompt_lines, build_color_script_guidance
from bookforge.page_architecture import plan_architecture_sequence, write_planning_artifacts as write_arch_planning_artifacts
from bookforge.page_architecture.prompting import build_architecture_negative_lines, build_architecture_prompt_lines, build_page_architecture_guidance
from bookforge.page_architecture.templates import architecture_templates
from bookforge.page_architecture.types import to_primitive as arch_to_primitive
from bookforge.profiles import apply_profile, load_profile
from bookforge.qc.image_qc import choose_best_variant, write_qa_report
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.qc.premium_visual_qc import run_premium_visual_qc
from bookforge.review.contact_sheet import generate_contact_sheet
from bookforge.review.html_report import generate_report as generate_html_report
from bookforge.review.proof_pack import generate_proof_pack, write_production_report
from bookforge.story.back_matter import generate_blurb_options
from bookforge.story.prompt_compiler import compile_prompt, tighten_prompt
from bookforge.story.story_spec import build_bible_variants, parse_story
from bookforge.story.storyboard import generate_storyboard




def _storyweaver_declared_pages(parsed: Dict[str, Any]) -> int | None:
    declared = parsed.get("metadata", {}).get("declared_pages")
    return int(declared) if isinstance(declared, int) and declared > 0 else None


def _storyweaver_spreads(parsed: Dict[str, Any]) -> List[List[int]]:
    spreads = parsed.get("metadata", {}).get("detected_spreads", [])
    out: List[List[int]] = []
    if isinstance(spreads, list):
        for pair in spreads:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                out.append([int(pair[0]), int(pair[1])])
    return out


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_planning_prompt_guidance(out: Path) -> Dict[int, Dict[str, Any]]:
    planning_dir = out / "preprod" / "planning"
    color_payload = _load_json_if_exists(planning_dir / "color_script.json") or {}
    emotion_payload = _load_json_if_exists(planning_dir / "emotion_analysis.json") or []
    arch_plan = _load_json_if_exists(planning_dir / "architecture_plan.json") or []

    emotion_by_page = {int(x.get("page_number", 0)): x for x in emotion_payload if isinstance(x, dict)}
    color_by_page = {int(x.get("page_number", 0)): x for x in color_payload.get("pages", []) if isinstance(x, dict)}
    arch_by_page = {int(x.get("page_number", 0)): x for x in arch_plan if isinstance(x, dict)}

    variants = {v.variant_id: v for v in architecture_templates()}

    page_numbers = sorted(set(color_by_page.keys()) | set(arch_by_page.keys()) | set(emotion_by_page.keys()))
    guidance: Dict[int, Dict[str, Any]] = {}
    for page_no in page_numbers:
        color_g = build_color_script_guidance(color_by_page.get(page_no), emotion_by_page.get(page_no))
        plan = arch_by_page.get(page_no)
        variant = None
        if plan:
            selected_variant = str(plan.get("selected_variant_id", ""))
            if selected_variant in variants:
                variant = {"zones": [arch_to_primitive(z) for z in variants[selected_variant].zones]}
        arch_g = build_page_architecture_guidance(plan, variant)
        prompt_lines = build_color_prompt_lines(color_g) + build_architecture_prompt_lines(arch_g)
        negative_lines = build_color_negative_lines(color_g) + build_architecture_negative_lines(arch_g)
        guidance[page_no] = {
            "color_script_guidance": color_g,
            "page_architecture_guidance": arch_g,
            "prompt_lines": prompt_lines,
            "negative_lines": negative_lines,
        }
    return guidance


def _load_color_scoring_context(out: Path) -> tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    planning_dir = out / "preprod" / "planning"
    color_payload = _load_json_if_exists(planning_dir / "color_script.json") or {}
    master_palette = _load_json_if_exists(planning_dir / "master_palette.json") or {}
    page_specs = color_payload.get("pages", []) if isinstance(color_payload, dict) else []
    page_spec_by_page = {int(x.get("page_number", 0)): x for x in page_specs if isinstance(x, dict)}
    return page_spec_by_page, master_palette if isinstance(master_palette, dict) else {}


def _load_architecture_scoring_context(out: Path) -> Dict[int, Dict[str, Any]]:
    planning_dir = out / "preprod" / "planning"
    arch_plan = _load_json_if_exists(planning_dir / "architecture_plan.json") or []
    if not isinstance(arch_plan, list) or not arch_plan:
        return {}
    variants = {v.variant_id: arch_to_primitive(v) for v in architecture_templates()}
    page_to_variant: Dict[int, Dict[str, Any]] = {}
    for item in arch_plan:
        if not isinstance(item, dict):
            continue
        page_no = int(item.get("page_number", 0) or 0)
        variant_id = str(item.get("selected_variant_id", ""))
        variant = variants.get(variant_id)
        if page_no > 0 and variant:
            page_to_variant[page_no] = variant
    return page_to_variant


def _build_prompt_addendum(page: Dict[str, Any], turn: Dict[str, Any], artifact: Dict[str, Any], editorial_mode: bool) -> str:
    parts: List[str] = []
    if turn:
        parts.append(f"This page sets up: {turn.get('recto_hook', '')}. The reveal comes next page: {turn.get('verso_payoff', '')}.")
    req_hidden = [str(x).strip() for x in page.get("required_hidden_details", []) if str(x).strip()]
    if req_hidden:
        parts.append("Required hidden details (must include): " + "; ".join(req_hidden) + ".")
    note = str(page.get("illustration_notes", "")).strip()
    if note:
        parts.append(f"ILLUSTRATION NOTE (must follow): {note}")
    if artifact:
        parts.append(f"Hidden artifact ({artifact.get('artifact_type', 'micro')}): {artifact.get('instruction', '')} Keep subtle. NO text/logos/watermarks.")
    if editorial_mode:
        eye = verify_focus_not_covered_by_panel((0.5, 0.9), (0.0, 0.8, 1.0, 1.0))
        if eye.get("status") == "warn":
            parts.append("keep key action above caption strip; keep faces away from bottom edge")
    return " ".join(p for p in parts if p)


def _write_companion_artifacts(preprod_dir: Path, parsed: Dict[str, Any], fallback_readaloud: str = "") -> None:
    companion = preprod_dir / "companion"
    companion.mkdir(parents=True, exist_ok=True)
    extras = parsed.get("metadata", {}).get("extras", {}) if isinstance(parsed.get("metadata", {}), dict) else {}
    mapping = {
        "READALOUD_NOTES.md": str(extras.get("readaloud_notes", "")).strip() or fallback_readaloud,
        "PARENTS_COMPANION.md": str(extras.get("parents_companion", "")).strip(),
        "DEVELOPMENTAL_ARCHITECTURE.md": str(extras.get("developmental_architecture", "")).strip(),
        "COMMERCIAL_ARCHITECTURE.md": str(extras.get("commercial_architecture_alignment", "")).strip(),
        "TAGLINE.md": str(extras.get("the_line_that_sells_the_book", "")).strip(),
    }
    for name, body in mapping.items():
        if body:
            (companion / name).write_text(body + ("\n" if not body.endswith("\n") else ""), encoding="utf-8")


def _copy_companion_to_review(out: Path) -> None:
    src = out / "preprod" / "companion"
    dst = out / "review" / "companion"
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.glob("*.md"):
        dst.joinpath(p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

def _seed_from_lock(title: str, author: str, approved_variant: int) -> int:
    payload = f"{title}|{author}|{approved_variant}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def _cache_key(prompt: str, endpoint: str, seed: int, size: tuple[int, int]) -> str:
    payload = f"{prompt}|{endpoint}|{seed}|{size[0]}x{size[1]}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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

def _studio_debug_enabled() -> bool:
    import os

    return str(os.getenv("BOOKFORGE_DEBUG_STUDIO", "")).strip().lower() in {"1", "true", "yes", "on"}


def _studio_debug(msg: str) -> None:
    if _studio_debug_enabled():
        print(f"[studio-debug] {msg}", flush=True)

def _fal_key_from_env() -> str:
    import os

    return (os.getenv("FAL_KEY") or os.getenv("Fal_key") or os.getenv("fal_key") or "").strip()


def _feature_flag(name: str, default: str = "true") -> bool:
    import os

    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}




class BookforgePipeline:
    def __init__(self) -> None:
        self.bleed_in = 0.125
        self.safe_in = 0.375
        self.default_steps = 6
        self.default_page_variants = 2

    def doctor(self, strict: bool = False) -> Dict[str, Any]:
        import os

        fal = bool(_fal_key_from_env())
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

    def preprod(self, story_path: str, out_dir: str, size: str, pages: int, variants: int, profile: str | None = None) -> Dict[str, Any]:
        out = Path(out_dir)
        preprod = out / "preprod"
        (preprod / "bible_variants").mkdir(parents=True, exist_ok=True)

        profile_dict = load_profile(profile) if profile else {}
        profile_meta = profile_dict.get("metadata", {}) if isinstance(profile_dict, dict) else {}
        parsed = parse_story(story_path, pages, max_words_per_page_override=profile_meta.get("max_words_per_page"))
        page_count = _storyweaver_declared_pages(parsed) or pages
        storyboard = generate_storyboard(parsed, variants)
        (preprod / "story_parsed.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        (preprod / "storyboard.json").write_text(json.dumps(storyboard, indent=2), encoding="utf-8")
        companion_dir = preprod / "companion"
        companion = parsed.get("companion", {}) if isinstance(parsed.get("companion", {}), dict) else {}
        if companion:
            companion_dir.mkdir(parents=True, exist_ok=True)
            for section, body in companion.items():
                slug = re.sub(r"[^a-z0-9]+", "_", str(section).strip().lower()).strip("_") or "section"
                (companion_dir / f"{slug}.md").write_text(str(body), encoding="utf-8")
            (companion_dir / "manifest.json").write_text(json.dumps({"sections": sorted(companion.keys())}, indent=2), encoding="utf-8")
        bible_variants = build_bible_variants(parsed, variants=variants)
        blurb_options = generate_blurb_options(parsed, n=5, allow_generated=False)
        (preprod / "blurb_options.json").write_text(json.dumps(blurb_options, indent=2), encoding="utf-8")

        for variant in bible_variants:
            folder = preprod / "bible_variants" / f"v{variant['variant']}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "character_bible.json").write_text(json.dumps(variant["character_bible"], indent=2), encoding="utf-8")
            (folder / "style_bible.json").write_text(json.dumps(variant["style_bible"], indent=2), encoding="utf-8")
            (folder / "prompt_prefix.txt").write_text(variant["locked_prompt_prefix"], encoding="utf-8")
            (folder / "negative_prompt.txt").write_text(variant["locked_negative_prompt"], encoding="utf-8")

        (preprod / "layout_options.json").write_text(json.dumps(presets_payload(), indent=2), encoding="utf-8")

        planning_dir = preprod / "planning"
        if _feature_flag("BOOKFORGE_COLOR_SCRIPT", default="true"):
            analyses, master_palette, page_specs, transitions = plan_color_script(parsed.get("pages", []))
            write_color_planning_artifacts(planning_dir, analyses, master_palette, page_specs, transitions)
        if _feature_flag("BOOKFORGE_PAGE_ARCHITECTURE", default="true"):
            source_pages = []
            if (planning_dir / "emotion_analysis.json").exists():
                source_pages = json.loads((planning_dir / "emotion_analysis.json").read_text(encoding="utf-8"))
            else:
                source_pages = [{"page_number": p.get("page_number", i + 1), "narrative_function": "rising_action"} for i, p in enumerate(parsed.get("pages", []))]
            architecture_plan, architecture_report = plan_architecture_sequence(source_pages, genre="picture_book")
            write_arch_planning_artifacts(planning_dir, architecture_plan, architecture_report)

        trim_w, trim_h = parse_trim_size(size)
        req_w = int((trim_w + 2 * self.bleed_in) * 300)
        req_h = int((trim_h + 2 * self.bleed_in) * 300)

        ill, provider_name = resolve_image_provider("auto")
        style_variants_dir = preprod / "style_variants"
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

            variant_dir = style_variants_dir / f"v{i}"
            variant_dir.mkdir(parents=True, exist_ok=True)
            references = {
                "variant_id": i,
                "provider": provider_name,
                "character_reference": str((preprod / "character_options" / f"character_turnaround_v{i}.png").relative_to(preprod)),
                "style_reference": str((preprod / "style_options" / f"style_frame_v{i}.png").relative_to(preprod)),
                "cover_sample": str((preprod / "cover_options" / f"cover_concept_v{i}.png").relative_to(preprod)),
                "prompt_prefix": variant["locked_prompt_prefix"],
                "negative_prompt": variant["locked_negative_prompt"],
                "settings": {"steps": self.default_steps, "required_pixels": [req_w, req_h]},
            }
            (variant_dir / "variant_review.json").write_text(json.dumps(references, indent=2), encoding="utf-8")

        option_images = sorted((preprod).rglob("*_v*.png"))
        generate_contact_sheet(option_images, preprod / "options_contact_sheet.pdf")

        _studio_debug("spread handling complete; rendering PDFs")
        engine = PDFLayoutEngine(font_path=Path("assets/fonts/NotoSans-Regular.ttf"))
        for p in INTERIOR_LAYOUT_PRESETS:
            engine.render_interior_preview(preprod / "layout_previews" / f"interior_preview_{p.id}.pdf", size, self.bleed_in, self.safe_in, p)
        for p in COVER_LAYOUT_PRESETS:
            engine.render_cover_preview(preprod / "cover_previews" / f"cover_preview_{p.id}.pdf", trim_w, trim_h, self.bleed_in, self.safe_in, p)

        story_text = "\n".join([p["text"] for p in parsed["pages"]])
        age_band = str(parsed.get("metadata", {}).get("age_band", "")).strip() or "6-8"
        editorial_dir = preprod / "editorial"
        editorial_dir.mkdir(parents=True, exist_ok=True)
        dual_address = analyze_dual_address(story_text, age_band)
        rhythm_report = audit_rhythm_and_rhyme(story_text)
        hook_pack = generate_hook_pack(story_text, age_band)
        page_turn_map = build_page_turn_map(parsed["pages"], age_band)
        artifact_plan_options = propose_artifact_options(age_band, {"motif": "star", "side_character": "tiny firefly", "token": "moon"})
        readaloud_script = generate_readaloud_script(parsed["pages"], rhythm_report, page_turn_map)
        _write_companion_artifacts(preprod, parsed, fallback_readaloud=readaloud_script)
        trade_dress = generate_trade_dress({}, get_preset(parsed["metadata"].get("cover_layout_preset", COVER_LAYOUT_PRESETS[0].id), "cover"), parsed["metadata"].get("palette", "#F2C14E,#3A506B").split(","))
        eye_flow_warnings = []
        for _p in parsed["pages"][:3]:
            eye_flow_warnings.append(verify_focus_not_covered_by_panel((0.5, 0.9), (0.0, 0.8, 1.0, 1.0)))
        selected_plan = artifact_plan_options.get("plans", [{}])[0]
        artifact_map = apply_artifact_plan_to_pages(selected_plan, parsed["pages"]) if selected_plan else []
        (editorial_dir / "dual_address.json").write_text(json.dumps(dual_address, indent=2), encoding="utf-8")
        (editorial_dir / "rhythm_report.json").write_text(json.dumps(rhythm_report, indent=2), encoding="utf-8")
        (editorial_dir / "hook_pack.json").write_text(json.dumps(hook_pack, indent=2), encoding="utf-8")
        (editorial_dir / "page_turn_map.json").write_text(json.dumps(page_turn_map, indent=2), encoding="utf-8")
        (editorial_dir / "artifact_plan_options.json").write_text(json.dumps(artifact_plan_options, indent=2), encoding="utf-8")
        (editorial_dir / "readaloud_script.md").write_text(readaloud_script, encoding="utf-8")
        (editorial_dir / "trade_dress.json").write_text(json.dumps(trade_dress, indent=2), encoding="utf-8")
        (editorial_dir / "hidden_artifacts_map.json").write_text(json.dumps(artifact_map, indent=2), encoding="utf-8")
        render_editorial_report_md(
            editorial_dir / "editorial_report.md",
            dual_address,
            rhythm_report,
            hook_pack,
            page_turn_map,
            {"selected_plan_id": selected_plan.get("plan_id", ""), "artifact_types_used": sorted({a.get('artifact_type', '') for a in artifact_map})},
            eye_flow_warnings,
            editorial_dir / "readaloud_script.md",
            trade_dress,
        )

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
            "image_provider": "auto",
            "spread_mode": "custom_pairs" if _storyweaver_spreads(parsed) else "none",
            "spread_pairs": _storyweaver_spreads(parsed),
            "checkpoint_pages": 2,
            "qa_profile": "platinum",
            "max_regen_rounds": 2,
            "min_sharpness": 120.0,
            "min_entropy": 3.5,
            "min_contrast": 25.0,
            "max_border_bar_score": 0.25,
            "min_style_hist_similarity": 0.65,
            "max_page_to_page_hist_drift": 0.45,
            "max_text_likelihood": 0.15,
            "max_watermark_likelihood": 0.15,
            "max_logo_likelihood": 0.20,
            "max_border_artifact_score": 0.25,
            "max_face_like_regions": 3,
            "max_focus_bleed_overlap": 0.15,
            "color_grade_mode": "match_style",
            "color_grade_strength": 0.35,
            "sharpen_amount": 0.15,
            "grain_amount": 0.05,
            "crop_mode": "smart",
            "director_grade_enabled": True,
            "tone_curve_preset": "storybook_lux",
            "tone_curve_strength": 0.35,
            "paper_texture_strength": 0.08,
            "paper_texture_scale": 1.0,
            "global_grade_strength": 0.30,
            "min_brightness_p05": 15,
            "max_brightness_p95": 245,
            "max_out_of_gamut_risk": 0.35,
            "max_book_palette_drift": 0.45,
            "pdf_image_embed": "jpeg",
            "pdf_jpeg_quality": 92,
            "preflight_max_interior_mb": 300,
            "approved_blurb_index": 0,
            "approved_subtitle_index": 0,
            "back_blurb_enabled": True,
            "allow_generated_back_copy": False,
            "back_cover_tagline_source": "story",
            "back_cover_blurb_source": "story",
            "age_band": age_band if age_band in {"3-5", "6-8", "7-12", "custom"} else "6-8",
            "editorial_mode": True,
            "artifact_plan_id": selected_plan.get("plan_id", "plan_1_light"),
            "artifact_intensity": "light",
            "readaloud_script_enabled": True,
            "trade_dress_lock_enabled": True,
            "allow_generated_cover_copy": False,
            "notes": "",
        }
        if profile_dict:
            approval = apply_profile(approval, profile_dict)
        (preprod / "APPROVAL.json").write_text(json.dumps(approval, indent=2), encoding="utf-8")
        warnings = parsed.get("parse_warnings", [])
        return {"status": "PASS", "stage": "preprod", "out_dir": str(out), "warnings": warnings, "declared_pages": parsed.get("metadata", {}).get("declared_pages", pages), "storyweaver_detected": bool(parsed.get("metadata", {}).get("storyweaver_detected", False))}

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
        parsed_story_path = preprod / "story_parsed.json"
        if not storyboard_path.exists():
            raise RuntimeError("Missing storyboard.json in preprod.")
        parsed_story = json.loads(parsed_story_path.read_text(encoding="utf-8")) if parsed_story_path.exists() else {"title": "book", "author": "author"}
        page_count = _storyweaver_declared_pages(parsed_story) or page_count

        approved_character = preprod / "character_options" / approval["approved_character"]
        approved_style = preprod / "style_options" / approval["approved_style"]
        approved_cover = preprod / "cover_options" / approval["approved_cover"]
        for path in [approved_character, approved_style, approved_cover]:
            if not path.exists():
                raise RuntimeError(f"Missing approval selection: {path}")

        effective_page_count = int(parsed_story.get("metadata", {}).get("declared_pages", page_count) or page_count)
        trim_w, trim_h = parse_trim_size(size)
        required_pixels = [int((trim_w + 2 * self.bleed_in) * 300), int((trim_h + 2 * self.bleed_in) * 300)]
        blurb_options = json.loads((preprod / "blurb_options.json").read_text(encoding="utf-8")) if (preprod / "blurb_options.json").exists() else {"blurbs": [], "subtitles": []}
        blurbs = blurb_options.get("blurbs", [])
        subtitles = blurb_options.get("subtitles", [])
        spine_w = max(float(approval["spine_min_in"]), effective_page_count * float(approval["paper_thickness_in"]))
        cover_preset = get_preset(approval["cover_layout_preset"], "cover")

        candidates = parsed_story.get("metadata", {}).get("back_cover_candidates", {}) if isinstance(parsed_story.get("metadata", {}), dict) else {}
        tagline = str(candidates.get("tagline_quote", "")).strip()
        one_pitch = str(candidates.get("one_sentence_pitch", "")).strip()
        if approval.get("allow_generated_back_copy", False):
            back_blurb = one_pitch or (blurbs[int(approval.get("approved_blurb_index", 0))] if blurbs else "")
            source_blurb = "story" if one_pitch else "generated"
            back_tagline = tagline
            source_tagline = "story" if tagline else "generated"
        else:
            back_blurb = one_pitch
            source_blurb = "story"
            back_tagline = tagline
            source_tagline = "story"

        provider_name = str(approval.get("image_provider", "auto")).lower()
        lock = {
            "approved_variant": variant,
            "image_provider": provider_name,
            "visual_lock": {
                "variant_id": variant,
                "character_reference": str(approved_character),
                "style_reference": str(approved_style),
                "cover_reference": str(approved_cover),
            },
            "approved_character": str(approved_character),
            "approved_style": str(approved_style),
            "approved_cover": str(approved_cover),
            "approved_character_reference": str(approved_character),
            "approved_style_reference": str(approved_style),
            "character_bible": json.loads((vv / "character_bible.json").read_text(encoding="utf-8")),
            "style_bible": json.loads((vv / "style_bible.json").read_text(encoding="utf-8")),
            "locked_prompt_prefix": (vv / "prompt_prefix.txt").read_text(encoding="utf-8"),
            "locked_negative_prompt": (vv / "negative_prompt.txt").read_text(encoding="utf-8"),
            "interior_layout_preset": approval["interior_layout_preset"],
            "typography_preset": approval["typography_preset"],
            "cover_layout_preset": approval["cover_layout_preset"],
            "storyboard": json.loads(storyboard_path.read_text(encoding="utf-8")),
            "print": {"trim_size": size, "bleed_in": self.bleed_in, "safe_in": self.safe_in, "dpi": 300, "page_count": effective_page_count, "required_pixels": required_pixels},
            "cover": {"paper_thickness_in": float(approval["paper_thickness_in"]), "spine_min_in": float(approval["spine_min_in"]), "spine_w_in": spine_w, "barcode_box_in": cover_preset["barcode_box_in"], "spine_text_min_in": 0.10},
            "fal": {"endpoint": approval.get("fal_endpoint", "https://fal.run/fal-ai/flux/schnell"), "steps": int(approval["image_steps"]), "page_variants": int(approval["page_variants"])},
            "qa": {k: approval[k] for k in ["qa_profile", "max_regen_rounds", "min_sharpness", "min_entropy", "min_contrast", "max_border_bar_score", "min_style_hist_similarity", "max_page_to_page_hist_drift", "max_text_likelihood", "max_watermark_likelihood", "max_logo_likelihood", "max_border_artifact_score", "max_face_like_regions", "max_focus_bleed_overlap", "min_brightness_p05", "max_brightness_p95", "max_out_of_gamut_risk", "max_book_palette_drift"]},
            "post": {
                "color_grade_mode": approval.get("color_grade_mode", "match_style"),
                "color_grade_strength": float(approval.get("color_grade_strength", 0.35)),
                "sharpen_amount": float(approval.get("sharpen_amount", 0.15)),
                "grain_amount": float(approval.get("grain_amount", 0.05)),
                "crop_mode": approval.get("crop_mode", "smart"),
                "director_grade_enabled": bool(approval.get("director_grade_enabled", True)),
                "tone_curve_preset": approval.get("tone_curve_preset", "storybook_lux"),
                "tone_curve_strength": float(approval.get("tone_curve_strength", 0.35)),
                "paper_texture_strength": float(approval.get("paper_texture_strength", 0.08)),
                "paper_texture_scale": float(approval.get("paper_texture_scale", 1.0)),
                "global_grade_strength": float(approval.get("global_grade_strength", 0.30)),
                "upscale_after_approval": approval.get("upscale_after_approval", "disabled"),
                "premium_finish_hooks": {
                    "texture_enhancement": approval.get("texture_enhancement", "enabled"),
                    "microcontrast_enhancement": approval.get("microcontrast_enhancement", "enabled"),
                    "anti_smoothing_pass": approval.get("anti_smoothing_pass", "enabled"),
                    "optional_tiled_upscale_path": approval.get("optional_tiled_upscale_path", "unavailable_noop"),
                    "structure_preserving_upscale_guidance": approval.get("structure_preserving_upscale_guidance", "unavailable_noop"),
                    "target_resolution": approval.get("target_resolution", "300dpi_trim_plus_bleed"),
                },
            },
            "pdf": {"image_embed": approval.get("pdf_image_embed", "jpeg"), "jpeg_quality": int(approval.get("pdf_jpeg_quality", 92)), "max_interior_mb": float(approval.get("preflight_max_interior_mb", 300))},
            "spreads": {
                "mode": "custom_pairs" if _storyweaver_spreads(parsed_story) else approval.get("spread_mode", "none"),
                "pairs": _storyweaver_spreads(parsed_story) or approval.get("spread_pairs", []),
            },
            "checkpoint": {"pages": int(approval.get("checkpoint_pages", 2))},
            "back_matter": {
                "enabled": bool(approval.get("back_blurb_enabled", True)),
                "blurb": back_blurb,
                "subtitle": (subtitles[int(approval.get("approved_subtitle_index", 0))] if subtitles else ""),
                "tagline": back_tagline,
            },
            "back_cover_copy": {
                "allow_generated_back_copy": bool(approval.get("allow_generated_back_copy", False)),
                "back_cover_tagline_source": source_tagline if back_tagline else "story",
                "back_cover_blurb_source": source_blurb if back_blurb else "story",
            },
        }
        editorial_dir = preprod / "editorial"
        if editorial_dir.exists():
            artifact_options = json.loads((editorial_dir / "artifact_plan_options.json").read_text(encoding="utf-8")) if (editorial_dir / "artifact_plan_options.json").exists() else {"plans": []}
            selected_id = approval.get("artifact_plan_id", "")
            selected_plan = next((p for p in artifact_options.get("plans", []) if p.get("plan_id") == selected_id), artifact_options.get("plans", [{}])[0])
            pages_source = json.loads((preprod / "story_parsed.json").read_text(encoding="utf-8")).get("pages", []) if (preprod / "story_parsed.json").exists() else []
            resolved_map = apply_artifact_plan_to_pages(selected_plan or {}, pages_source) if selected_plan else []
            lock["editorial"] = {
                "age_band": approval.get("age_band", "6-8"),
                "artifact_plan_id": approval.get("artifact_plan_id", ""),
                "artifact_intensity": approval.get("artifact_intensity", "light"),
                "readaloud_script_enabled": bool(approval.get("readaloud_script_enabled", True)),
                "trade_dress_lock_enabled": bool(approval.get("trade_dress_lock_enabled", True)),
                "editorial_mode": bool(approval.get("editorial_mode", True)),
                "resolved_artifact_plan": selected_plan,
                "resolved_artifacts_map": resolved_map,
                "hook_pack": json.loads((editorial_dir / "hook_pack.json").read_text(encoding="utf-8")) if (editorial_dir / "hook_pack.json").exists() else {},
                "page_turn_map": json.loads((editorial_dir / "page_turn_map.json").read_text(encoding="utf-8")) if (editorial_dir / "page_turn_map.json").exists() else [],
            }
        else:
            print("WARN: editorial folder missing; continuing for backward compatibility")
        base_seed = _seed_from_lock(parsed_story.get("title", "book"), parsed_story.get("author", "author"), lock["approved_variant"])
        lock["seeds"] = {"base_seed": base_seed, "per_page_seed": {str(i): base_seed + i * 101 for i in range(1, effective_page_count + 1)}}
        lock, _lock_prov = normalize_visual_lock(lock, parsed_story=parsed_story, approval=approval)
        lock["review_provenance"] = {"visual_contract_applied": _lock_prov.get("applied_fields", [])}
        if lock["spreads"].get("pairs") and lock["spreads"].get("mode") == "none":
            lock["spreads"]["mode"] = "custom_pairs"
        if not lock["spreads"]["pairs"] and approval.get("spread_pages"):
            pages = approval.get("spread_pages", [])
            if isinstance(pages, list) and len(pages) >= 2:
                lock["spreads"]["mode"] = "custom_pairs"
                lock["spreads"]["pairs"] = [[int(pages[0]), int(pages[1])]]

        _parse_spread_pairs(lock["spreads"], effective_page_count)
        vres = validate_visual_lock(lock, require_lock=True)
        if not vres.ok:
            raise RuntimeError(f"LOCK.json missing required fields: {', '.join(vres.missing)}")
        (out / "LOCK.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        return {"status": "PASS", "lock": str(out / "LOCK.json"), "page_count": effective_page_count}

    def _split_spread(self, spread: Path, left_out: Path, right_out: Path) -> None:
        with Image.open(spread) as im:
            w, h = im.size
            half = w // 2
            im.crop((0, 0, half, h)).save(left_out, "PNG")
            im.crop((half, 0, w, h)).save(right_out, "PNG")


    def _validate_lock(self, lock: Dict[str, Any], require_lock: bool = False) -> None:
        vres = validate_visual_lock(lock, require_lock=require_lock)
        if not vres.ok:
            raise RuntimeError(f"LOCK.json missing required fields: {', '.join(vres.missing)}")
        lock, _ = normalize_visual_lock(lock)
        ensure_reference_paths_exist(lock)

    def _postprocess_variant(self, src: Path, dst: Path, style_ref: Path, lock: Dict[str, Any], page_no: int) -> None:
        post = lock.get("post", {})
        mode = str(post.get("color_grade_mode", "match_style"))
        strength = float(post.get("color_grade_strength", 0.35))
        sharpen = float(post.get("sharpen_amount", 0.15))
        grain = float(post.get("grain_amount", 0.05))
        palette = lock.get("style_bible", {}).get("palette", [])
        graded = grade_image(src, style_ref, palette, mode=mode, strength=strength)
        graded = apply_director_grade(
            graded,
            base_seed=int(lock.get("seeds", {}).get("base_seed", 0)),
            page_no=page_no,
            enabled=bool(post.get("director_grade_enabled", True)),
            tone_curve_preset=str(post.get("tone_curve_preset", "storybook_lux")),
            tone_curve_strength=float(post.get("tone_curve_strength", 0.35)),
            paper_texture_strength=float(post.get("paper_texture_strength", 0.08)),
            paper_texture_scale=float(post.get("paper_texture_scale", 1.0)),
            global_grade_strength=float(post.get("global_grade_strength", 0.30)),
        )
        grain_seed = int(lock.get("seeds", {}).get("base_seed", 0)) + int(page_no) * 997
        final = add_sharpen_and_grain(graded, sharpen_amount=sharpen, grain_amount=grain, grain_seed=grain_seed)
        final = apply_microtexture_enhancement(final)
        final = apply_canvas_grain(final)
        final = apply_paint_variance(final)
        # premium finish hooks are additive; unavailable external stacks remain explicit no-op
        _hooks = post.get("premium_finish_hooks", {})
        _ = _hooks.get("optional_tiled_upscale_path", "unavailable_noop")
        dst.parent.mkdir(parents=True, exist_ok=True)
        final.save(dst, "PNG")

    def _write_quality_summary(self, out: Path, qa_attempts: List[Dict[str, Any]], cache_hits: Dict[int, List[bool]], lock: Dict[str, Any]) -> Path:
        review = out / "review"
        review.mkdir(parents=True, exist_ok=True)
        summary_path = review / "quality_summary.md"
        best_by_page: Dict[str, Dict[str, Any]] = {}
        regenerated = set()
        integrity = set()
        for item in qa_attempts:
            page = str(item.get("page"))
            attempt = int(item.get("attempt", 1))
            if attempt > 1 and page.isdigit():
                regenerated.add(int(page))
            best = item.get("best", {})
            if page.isdigit() and (page not in best_by_page or attempt >= int(best_by_page[page].get("attempt", 0))):
                best_by_page[page] = {"attempt": attempt, "score": float(best.get("sharpness", 0.0) + best.get("contrast", 0.0) + best.get("entropy", 0.0)), "integrity": best}
            if best.get("text_likelihood", 0) > lock["qa"]["max_text_likelihood"] or best.get("watermark_likelihood", 0) > lock["qa"]["max_watermark_likelihood"] or best.get("logo_likelihood", 0) > lock["qa"]["max_logo_likelihood"]:
                if page.isdigit():
                    integrity.add(int(page))

        worst = sorted(((int(k), v["score"]) for k, v in best_by_page.items()), key=lambda x: x[1])[:5]
        total = sum(len(v) for v in cache_hits.values())
        hits = sum(1 for vv in cache_hits.values() for b in vv if b)
        rate = (hits / total) if total else 0.0

        lines = [
            "# Quality Summary",
            "",
            "## Top 5 Worst Pages by QA Score",
        ]
        if worst:
            lines.extend([f"- Page {p}: score {score:.2f}" for p, score in worst])
        else:
            lines.append("- None")
        lines.extend(["", "## Pages Regenerated", *([f"- {p}" for p in sorted(regenerated)] or ["- None"])])
        drift_pages = sorted(((int(k), float(v["integrity"].get("color_drift_vs_style", 0.0))) for k, v in best_by_page.items()), key=lambda x: x[1], reverse=True)[:5]
        lines.extend(["", "## Pages with Integrity Warnings (text/watermark/logo)", *([f"- {p}" for p in sorted(integrity)] or ["- None"])])
        lines.extend(["", "## Top Drift Pages", *([f"- Page {p}: drift {d:.3f}" for p, d in drift_pages] or ["- None"])])
        lines.extend(["", "## Cache Hit Rate", f"- {hits}/{total} ({rate:.1%})"])
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return summary_path

    def studio(self, story_path: str, out_dir: str, size: str, pages: int, illustrator: str, require_lock: bool) -> Dict[str, Any]:
        if illustrator == "openai":
            raise RuntimeError(OPENAI_DISABLED_MESSAGE)
        if illustrator not in {"fal", "auto", "flux_local"}:
            raise RuntimeError("Only Fal/Flux is supported for studio generation.")
        out = Path(out_dir)
        lock_path = out / "LOCK.json"
        if require_lock and not lock_path.exists():
            raise RuntimeError("LOCK.json missing. Run preprod + lock before studio.")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self._validate_lock(lock, require_lock=require_lock)

        requested_provider = illustrator if illustrator != "auto" else str(lock.get("image_provider", "auto"))
        endpoint = lock.get("fal", {}).get("endpoint", "https://fal.run/fal-ai/flux/schnell")
        ill, provider_name = resolve_image_provider(requested_provider, fal_endpoint=endpoint)

        parsed = parse_story(story_path, pages)
        page_count = _storyweaver_declared_pages(parsed) or len(parsed["pages"])
        storyboard_pages = {p["page_number"]: p for p in lock["storyboard"].get("pages", [])}
        req_w, req_h = lock["print"]["required_pixels"]

        prompts = []
        planning_prompt_guidance = _build_planning_prompt_guidance(out)
        color_spec_by_page, master_palette = _load_color_scoring_context(out)
        architecture_by_page = _load_architecture_scoring_context(out)
        _studio_debug("studio start: building prompts")
        turn_map = {int(x.get("page_number", 0)): x for x in lock.get("editorial", {}).get("page_turn_map", []) if isinstance(x, dict)}
        artifact_map = {int(x.get("page_number", 0)): x for x in lock.get("editorial", {}).get("resolved_artifacts_map", []) if isinstance(x, dict)}
        for p in parsed["pages"]:
            sb = storyboard_pages.get(p["page_number"], {})
            turn = turn_map.get(p["page_number"], {})
            artifact = artifact_map.get(p["page_number"], {})
            page_plan = planning_prompt_guidance.get(int(p["page_number"]), {})
            planning_lines = page_plan.get("prompt_lines", [])
            addendum = _build_prompt_addendum(p, turn, artifact, bool(lock.get("editorial", {}).get("editorial_mode", True)))
            addendum = " ".join([addendum] + [str(x) for x in planning_lines if str(x).strip()]).strip()
            prompt = compile_prompt(lock, p["text"], sb, addendum=addendum)
            prompt_negative_lines = page_plan.get("negative_lines", [])
            prompts.append(
                {
                    "page_number": p["page_number"],
                    "prompt": prompt + (" " + " ".join(prompt_negative_lines) if prompt_negative_lines else ""),
                    "illustration_notes": p.get("illustration_notes", ""),
                    "required_hidden_details": p.get("required_hidden_details", []),
                    "reference_images": [lock.get("approved_character_reference", lock.get("approved_character", "")), lock.get("approved_style_reference", lock.get("approved_style", ""))],
                }
            )

        prompt_contract = build_prompt_contract(parsed, lock, spread_pairs=lock.get("spreads", {}).get("pairs", []), planning_guidance=planning_prompt_guidance)

        checkpoint_pages = int(lock.get("checkpoint", {}).get("pages", 0))
        check_file = out / "CHECKPOINT.json"
        if checkpoint_pages > 0 and not (check_file.exists() and json.loads(check_file.read_text(encoding="utf-8")).get("approved")):
            checkpoint_prompts = prompts[:checkpoint_pages]
            checkpoint_generated = ill.generate_page_variants(
                checkpoint_prompts,
                out / "images" / "checkpoint_variants",
                (req_w, req_h),
                1,
                Path(lock.get("approved_character_reference", lock["approved_character"])),
                Path(lock.get("approved_style_reference", lock["approved_style"])),
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
        (out / "prompts.json").write_text(json.dumps({"prompts": prompts, "prompt_contract": prompt_contract, "checkpoint": checkpoint_summary}, indent=2), encoding="utf-8")

        page_seeds = {int(k): int(v) for k, v in lock.get("seeds", {}).get("per_page_seed", {}).items()}
        _studio_debug(f"starting full-page generation for {len(prompts)} pages")
        generated = ill.generate_page_variants(
            prompts,
            out / "images" / "variants_raw",
            (req_w, req_h),
            lock["fal"]["page_variants"],
            Path(lock.get("approved_character_reference", lock["approved_character"])),
            Path(lock.get("approved_style_reference", lock["approved_style"])),
            Path(lock["approved_style"]).with_name(f"palette_tile_v{lock['approved_variant']}.png"),
            lock["fal"]["steps"],
            seeds=page_seeds,
            cache_dir=out / "cache",
        )

        selected, upscaled_pages, qa_attempts = [], [], []
        selected_dir = out / "images"
        selected_dir.mkdir(parents=True, exist_ok=True)
        prev_ref = None
        force_regen_set = {int(p) for p in checkpoint_summary.get("force_regen", [])}
        variant_pref = {int(k): int(v) for k, v in checkpoint_summary.get("variant_preference", {}).items()}

        _studio_debug("starting per-page QA selection/regeneration loop")
        for page in parsed["pages"]:
            no = page["page_number"]
            raw_variant_paths = _order_variants([Path(p) for p in generated["variants"][no]], variant_pref.get(no))
            variant_paths = []
            for raw_path in raw_variant_paths:
                graded_path = out / "images" / "variants" / raw_path.name
                self._postprocess_variant(raw_path, graded_path, Path(lock["approved_style"]), lock, no)
                variant_paths.append(graded_path)
            best_path, qa = choose_best_variant(
                variant_paths,
                lock["qa"],
                Path(lock["approved_style"]),
                prev_ref,
                page_number=no,
                page_color_spec=color_spec_by_page.get(no),
                master_palette=master_palette,
                page_text=str(page.get("text", "")),
                architecture_variant=architecture_by_page.get(no),
                age_range=str(lock.get("editorial", {}).get("age_band", "")),
            )
            qa_attempts.append({"page": no, "attempt": 1, **qa})
            rounds = 0
            hard_prompt = prompts[no - 1]["prompt"]
            needs_forced_regen = no in force_regen_set
            while ((not qa["passes"]) or needs_forced_regen) and rounds < lock["qa"]["max_regen_rounds"]:
                rounds += 1
                needs_forced_regen = False
                hard_prompt = tighten_prompt(hard_prompt, ["anatomy", "artifact", "text"])
                regen = ill.generate_page_variants([{"page_number": no, "prompt": hard_prompt}], out / "images" / "variants_raw", (req_w, req_h), lock["fal"]["page_variants"], Path(lock.get("approved_character_reference", lock["approved_character"])), Path(lock.get("approved_style_reference", lock["approved_style"])), None, lock["fal"]["steps"], seeds={no: page_seeds.get(no, 0) + rounds * 1000}, cache_dir=out / "cache")
                regen_raw = _order_variants([Path(p) for p in regen["variants"][no]], variant_pref.get(no))
                regen_variants = []
                for raw_path in regen_raw:
                    graded_path = out / "images" / "variants" / raw_path.name
                    self._postprocess_variant(raw_path, graded_path, Path(lock["approved_style"]), lock, no)
                    regen_variants.append(graded_path)
                best_path, qa = choose_best_variant(
                    regen_variants,
                    lock["qa"],
                    Path(lock["approved_style"]),
                    prev_ref,
                    page_number=no,
                    page_color_spec=color_spec_by_page.get(no),
                    master_palette=master_palette,
                    page_text=str(page.get("text", "")),
                    architecture_variant=architecture_by_page.get(no),
                    age_range=str(lock.get("editorial", {}).get("age_band", "")),
                )
                if qa.get("best", {}).get("focus_bleed_overlap", 0.0) > lock["qa"].get("max_focus_bleed_overlap", 0.15):
                    hard_prompt = f"{hard_prompt} subject centered within safe area, keep key action away from edges"
                qa_attempts.append({"page": no, "attempt": rounds + 1, **qa})

            dst = selected_dir / f"page_{no:03d}.png"
            with Image.open(best_path) as im:
                work = im.convert("RGB")
                if work.width < req_w or work.height < req_h:
                    scale = max(req_w / work.width, req_h / work.height)
                    work = work.resize((math.ceil(work.width * scale), math.ceil(work.height * scale)), Image.Resampling.LANCZOS)
                    upscaled_pages.append(no)
                crop_mode = str(lock.get("post", {}).get("crop_mode", "smart")).lower()
                if work.width != req_w or work.height != req_h:
                    if crop_mode == "smart":
                        work = smart_crop_to_target(work, req_w, req_h)
                    else:
                        left = (work.width - req_w) // 2
                        top = (work.height - req_h) // 2
                        work = work.crop((left, top, left + req_w, top + req_h))
                work.save(dst, "PNG")
            qa_attempts[-1]["crop_method"] = "smart" if str(lock.get("post", {}).get("crop_mode", "smart")).lower() == "smart" else "center"
            selected.append(str(dst))
            prev_ref = dst

        _studio_debug("completed per-page selection; entering spread handling")
        spread_pairs = _parse_spread_pairs(lock.get("spreads", {}), page_count)

        upscale_setting = str(lock.get("post", {}).get("upscale_after_approval", "disabled")).strip().lower()
        if upscale_setting in {"enabled", "true", "1", "yes", "on"}:
            upscaled_selected: List[str] = []
            for src in selected:
                upscaled_selected.append(str(upscale_image(Path(src))))
            selected = upscaled_selected
        _studio_debug(f"spread pairs to process: {len(spread_pairs)}")
        for a, b in spread_pairs:
            spread_prompt = prompts[a - 1]["prompt"] + " panoramic double-page spread"
            spread_ok = False
            spread_round = 0
            spread_path: Path | None = None
            while not spread_ok and spread_round <= lock["qa"]["max_regen_rounds"]:
                spread_round += 1
                spread = ill.generate_page_variants([{"page_number": a, "prompt": spread_prompt}], out / "images" / "variants_raw", (req_w * 2, req_h), 1, Path(lock.get("approved_character_reference", lock["approved_character"])), Path(lock.get("approved_style_reference", lock["approved_style"])), None, lock["fal"]["steps"], seeds={a: page_seeds.get(a, 0)}, cache_dir=out / "cache")
                spread_path = Path(spread["variants"][a][0])
                spread_graded = out / "images" / "variants" / spread_path.name
                self._postprocess_variant(spread_path, spread_graded, Path(lock["approved_style"]), lock, a)
                _, spread_qa = choose_best_variant(
                    [spread_graded],
                    lock["qa"],
                    Path(lock["approved_style"]),
                    None,
                    page_number=a,
                    page_color_spec=color_spec_by_page.get(a),
                    master_palette=master_palette,
                    page_text=str(parsed["pages"][a - 1].get("text", "")) if a - 1 < len(parsed["pages"]) else "",
                    architecture_variant=architecture_by_page.get(a),
                    age_range=str(lock.get("editorial", {}).get("age_band", "")),
                )
                qa_attempts.append({"page": f"{a}-{b}", "attempt": spread_round, "spread": True, **spread_qa})
                if not spread_qa["passes"]:
                    continue
                self._split_spread(spread_path, Path(selected[a - 1]), Path(selected[b - 1]))
                left_best, left_qa = choose_best_variant(
                    [Path(selected[a - 1])],
                    lock["qa"],
                    Path(lock["approved_style"]),
                    Path(selected[a - 2]) if a > 1 else None,
                    page_number=a,
                    page_color_spec=color_spec_by_page.get(a),
                    master_palette=master_palette,
                    page_text=str(parsed["pages"][a - 1].get("text", "")) if a - 1 < len(parsed["pages"]) else "",
                    architecture_variant=architecture_by_page.get(a),
                    age_range=str(lock.get("editorial", {}).get("age_band", "")),
                )
                right_best, right_qa = choose_best_variant(
                    [Path(selected[b - 1])],
                    lock["qa"],
                    Path(lock["approved_style"]),
                    Path(selected[a - 1]),
                    page_number=b,
                    page_color_spec=color_spec_by_page.get(b),
                    master_palette=master_palette,
                    page_text=str(parsed["pages"][b - 1].get("text", "")) if b - 1 < len(parsed["pages"]) else "",
                    architecture_variant=architecture_by_page.get(b),
                    age_range=str(lock.get("editorial", {}).get("age_band", "")),
                )
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
        engine.render_interior(parsed["pages"], selected, interior, size, self.bleed_in, self.safe_in, get_preset(lock["interior_layout_preset"], "interior"), get_preset(lock["typography_preset"], "typography"), lock.get("pdf", {}), spread_pairs=spread_pairs)
        page_plan = {"declared_page_count": page_count, "actual_pages": len(parsed["pages"]), "spread_pairs": spread_pairs}
        (out / "page_plan.json").write_text(json.dumps(page_plan, indent=2), encoding="utf-8")
        cover_config = dict(lock["cover"])
        cover_config["subtitle"] = lock.get("back_matter", {}).get("subtitle", "")
        cover_config["back_blurb"] = lock.get("back_matter", {}).get("blurb", "") if lock.get("back_matter", {}).get("enabled", True) else ""
        engine.render_cover_wrap(cover, guides, trim_w, trim_h, self.bleed_in, self.safe_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], parsed["title"], parsed["author"], Path(lock["approved_cover"]), Path(lock["approved_style"]), get_preset(lock["cover_layout_preset"], "cover"), cover_config)

        _studio_debug("PDFs rendered; running preflight and review packaging")
        preflight = KDPPreflight().run(interior, cover, selected, trim_w, trim_h, self.bleed_in, len(parsed["pages"]), lock["cover"]["spine_w_in"], upscaled_pages, lock["cover"], self.safe_in, float(lock.get("pdf", {}).get("max_interior_mb", 300)))
        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")

        review = out / "review"
        architecture_review = []
        for attempt in qa_attempts:
            best = attempt.get("best", {}) if isinstance(attempt, dict) else {}
            metadata = best.get("metadata", {}) if isinstance(best, dict) else {}
            arch = metadata.get("page_architecture_score") if isinstance(metadata, dict) else None
            if arch:
                architecture_review.append(
                    {
                        "page": attempt.get("page"),
                        "attempt": attempt.get("attempt"),
                        "variant_path": best.get("path", ""),
                        "architecture_score": arch,
                    }
                )
        if architecture_review:
            review.mkdir(parents=True, exist_ok=True)
            (review / "page_architecture_scores.json").write_text(json.dumps(architecture_review, indent=2), encoding="utf-8")
        generate_contact_sheet([Path(p) for p in selected], review / "contact_sheet.pdf")
        cache_hits = generated.get("cache_hits", {})
        cache_keys = generated.get("cache_keys", {})
        if spread_pairs:
            generate_contact_sheet([Path(p) for p in selected], review / "spread_preview.pdf", columns=2)
        proof_meta = {"trim": size, "dpi": lock["print"]["dpi"], "cover_preset": lock["cover_layout_preset"], "interior_preset": lock["interior_layout_preset"], "endpoint": lock["fal"]["endpoint"], "provider": provider_name, "locked_references_used": True, "chosen_variant": lock["approved_variant"], "age_band": lock.get("editorial", {}).get("age_band", ""), "premise": lock.get("editorial", {}).get("hook_pack", {}).get("one_sentence_premise", ""), "artifact_intensity": lock.get("editorial", {}).get("artifact_intensity", "light"), "readaloud_enabled": lock.get("editorial", {}).get("readaloud_script_enabled", True)}
        generate_proof_pack(review / "proof_pack.pdf", cover, [Path(p) for p in selected], proof_meta, qa_attempts)
        drift_rows = [a.get("best", {}).get("color_drift_vs_style", 0.0) for a in qa_attempts if isinstance(a.get("page"), int)]
        drift_pages = sorted(
            [{"page": a.get("page"), "drift": float(a.get("best", {}).get("color_drift_vs_style", 0.0))} for a in qa_attempts if isinstance(a.get("page"), int)],
            key=lambda x: x["drift"],
            reverse=True,
        )[:5]
        cache_bools = [hit for arr in cache_hits.values() for hit in arr]
        cache_hit_rate = (sum(1 for x in cache_bools if x) / len(cache_bools)) if cache_bools else 0.0
        production_payload = {"lock_summary": {"approved_variant": lock["approved_variant"], "back_matter": lock.get("back_matter", {}), "provider": provider_name, "locked_references_used": True, "character_reference": lock.get("approved_character"), "style_reference": lock.get("approved_style")}, "seed_plan": lock.get("seeds", {}), "qa_thresholds": lock.get("qa", {}), "post": lock.get("post", {}), "pdf": lock.get("pdf", {}), "regen_counts": {str(p["page"]): p.get("attempt", 1) for p in qa_attempts}, "spread_pairs": spread_pairs, "checkpoint_overrides_applied": checkpoint_summary, "drift": {"mean": float(sum(drift_rows)/len(drift_rows)) if drift_rows else 0.0, "top_pages": drift_pages}, "cache_hit_rate": cache_hit_rate, "provider": {"name": provider_name, "endpoint": generated.get("endpoint", endpoint)}, "editorial": {"age_band": lock.get("editorial", {}).get("age_band", "6-8"), "artifact_intensity": lock.get("editorial", {}).get("artifact_intensity", "light"), "readaloud_script_enabled": lock.get("editorial", {}).get("readaloud_script_enabled", True), "premise": lock.get("editorial", {}).get("hook_pack", {}).get("one_sentence_premise", "")}, "font_runtime": {"font_name": getattr(engine, "font_name", ""), "fallback_reason": getattr(engine, "font_fallback_reason", "")}}
        write_production_report(review / "production_report.json", production_payload)
        self._write_quality_summary(out, qa_attempts, cache_hits, lock)
        _studio_debug("running premium visual QC")
        premium_qc = run_premium_visual_qc(
            [Path(p) for p in selected],
            lock=lock,
            parsed_story=parsed,
            provider_provenance={"provider": provider_name, "endpoint": generated.get("endpoint", endpoint), "generated_provenance": generated.get("provenance", {})},
        )
        qa_payload = {
            "attempts": qa_attempts,
            "profile": lock["qa"],
            "checkpoint_overrides_applied": checkpoint_summary,
            "cache_hits": cache_hits,
            "cache_keys": cache_keys,
            "post": lock.get("post", {}),
            "premium_visual_qc": premium_qc,
        }
        write_qa_report(review / "qa_report.json", qa_payload)
        (review / "visual_critic_report.json").write_text(
            json.dumps(
                {
                    "status": premium_qc.get("status"),
                    "thresholds": premium_qc.get("visual_critic_thresholds", {}),
                    "pages": [
                        {
                            "page": row.get("page"),
                            "scores": row.get("visual_critic_scores", {}),
                            "failures": row.get("visual_critic_failures", []),
                            "continuity": row.get("continuity", {}),
                            "continuity_warnings": row.get("continuity_warnings", []),
                        }
                        for row in premium_qc.get("pages", [])
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        preprod_editorial = out / "preprod" / "editorial"
        _copy_companion_to_review(out)
        if preprod_editorial.exists():
            for src, dst in [
                (preprod_editorial / "editorial_report.md", review / "editorial_report.md"),
                (preprod_editorial / "readaloud_script.md", review / "readaloud_script.md"),
                (preprod_editorial / "hook_pack.json", review / "hook_pack.json"),
                (preprod_editorial / "page_turn_map.json", review / "page_turn_map.json"),
            ]:
                if src.exists():
                    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            resolved = lock.get("editorial", {}).get("resolved_artifacts_map", [])
            (review / "hidden_artifacts_map.json").write_text(json.dumps(resolved, indent=2), encoding="utf-8")
        preprod_companion = out / "preprod" / "companion"
        if preprod_companion.exists():
            review_companion = review / "companion"
            if review_companion.exists():
                shutil.rmtree(review_companion)
            shutil.copytree(preprod_companion, review_companion)
        generate_html_report(out, [Path(p) for p in selected], qa_payload, production_payload, Path(lock["approved_cover"]))

        _studio_debug("writing final package zip")
        zip_path = out / "bookforge_package.zip"
        self._create_package(zip_path, out)
        return {"status": preflight["status"], "out_dir": str(out), "zip": str(zip_path)}

    def _expected_package_artifacts(self) -> List[str]:
        return [
            "interior.pdf",
            "cover_wrap.pdf",
            "cover_guides.pdf",
            "preflight_report.json",
            "LOCK.json",
            "prompts.json",
            "review/contact_sheet.pdf",
            "review/quality_summary.md",
            "review/proof_pack.pdf",
            "review/production_report.json",
            "review/qa_report.json",
            "review/visual_critic_report.json",
            "review/report.html",
        ]

    def verify(self, out_dir: str) -> Dict[str, Any]:
        out = Path(out_dir)
        required = self._expected_package_artifacts() + ["review/thumbs"]
        missing = [rel for rel in required if not (out / rel).exists()]
        warnings: List[str] = []
        failures: List[str] = []
        if missing:
            failures.append(f"Missing required artifacts: {', '.join(missing)}")

        preflight_path = out / "preflight_report.json"
        if preflight_path.exists():
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            if preflight.get("status") == "FAIL":
                failures.append("preflight_report.json status is FAIL")

        production_path = out / "review" / "production_report.json"
        if production_path.exists():
            production = json.loads(production_path.read_text(encoding="utf-8"))
            post = production.get("post", {})
            required_post = {"crop_mode", "director_grade_enabled", "tone_curve_preset"}
            missing_post = sorted(required_post - set(post.keys()))
            if missing_post:
                failures.append(f"production_report.json post missing fields: {', '.join(missing_post)}")
            for field in ["post", "qa_thresholds", "cache_hit_rate"]:
                if field not in production:
                    failures.append(f"production_report.json missing {field}")
            editorial = production.get("editorial")
            if editorial:
                for field in ["age_band", "artifact_intensity", "readaloud_script_enabled"]:
                    if field not in editorial:
                        failures.append(f"production_report.json editorial missing {field}")

        review_dir = out / "review"
        page_plan_path = out / "page_plan.json"
        if page_plan_path.exists():
            page_plan = json.loads(page_plan_path.read_text(encoding="utf-8"))
            declared = int(page_plan.get("declared_page_count", 0))
            actual = int(page_plan.get("actual_pages", 0))
            if declared and actual and declared != actual:
                failures.append(f"page_plan.json declared_page_count ({declared}) != actual_pages ({actual})")
            if not page_plan.get("spread_pairs"):
                warnings.append("page_plan.json has no spread pairs")

        companion_dir = review_dir / "companion"
        if companion_dir.exists():
            for cname in ["READALOUD_NOTES.md", "PARENTS_COMPANION.md", "DEVELOPMENTAL_ARCHITECTURE.md", "COMMERCIAL_ARCHITECTURE.md", "TAGLINE.md"]:
                if not (companion_dir / cname).exists():
                    warnings.append(f"Missing review/companion/{cname}")

        if not (review_dir / "editorial_report.md").exists():
            warnings.append("Missing review/editorial_report.md")
        companion_dir = review_dir / "companion"
        story_parsed_path = out / "preprod" / "story_parsed.json"
        expects_companion = False
        if story_parsed_path.exists():
            parsed_story = json.loads(story_parsed_path.read_text(encoding="utf-8"))
            expects_companion = bool(parsed_story.get("metadata", {}).get("storyweaver_detected", False))
        if expects_companion and not companion_dir.exists():
            warnings.append("Missing review/companion (allowed for older runs)")
        prod = json.loads(production_path.read_text(encoding="utf-8")) if production_path.exists() else {}
        if prod.get("editorial", {}).get("readaloud_script_enabled", True) and not (review_dir / "readaloud_script.md").exists():
            warnings.append("Missing review/readaloud_script.md")

        zip_path = out / "bookforge_package.zip"
        if zip_path.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
            expected = set(self._expected_package_artifacts())
            missing_zip = sorted(expected - names)
            if missing_zip:
                failures.append(f"bookforge_package.zip missing artifacts: {', '.join(missing_zip)}")
            if companion_dir.exists() and not any(n.startswith("review/companion/") for n in names):
                failures.append("bookforge_package.zip missing review/companion artifacts")
        else:
            warnings.append("bookforge_package.zip not found; run studio packaging step")

        status = "PASS"
        if failures:
            status = "FAIL"
        elif warnings:
            status = "WARN"
        return {"status": status, "failures": failures, "warnings": warnings}

    def _create_package(self, zip_path: Path, out: Path) -> None:
        include = self._expected_package_artifacts()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in include:
                path = out / rel
                if path.exists():
                    zf.write(path, arcname=rel)
            for p in (out / "images").rglob("*.png"):
                zf.write(p, arcname=str(p.relative_to(out)))
            thumbs = out / "review" / "thumbs"
            if thumbs.exists():
                for p in thumbs.rglob("*"):
                    if p.is_file():
                        zf.write(p, arcname=str(p.relative_to(out)))
            companion = out / "review" / "companion"
            if companion.exists():
                for p in companion.rglob("*.md"):
                    zf.write(p, arcname=str(p.relative_to(out)))
