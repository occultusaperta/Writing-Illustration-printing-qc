from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from bookforge.illustration.fal_flux import FalFluxIllustrator, PlaceholderIllustrator
from bookforge.illustration.openai_images import OpenAIImagesIllustrator
from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.story.agent import StoryAgent


class BookforgePipeline:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()
        self.layout = PDFLayoutEngine()
        self.preflight = KDPPreflight()

    def doctor(self, strict: bool = False) -> Dict[str, Any]:
        loaded = self.loader.load()
        required = [Path(self.loader.knowledge_root / p) for p in self.loader.REQUIRED_JSON]
        missing = [str(p) for p in required if not p.exists()]
        can_auto_real = bool(os.getenv("FAL_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip())
        issues = []
        if strict:
            if not can_auto_real:
                issues.append("auto illustrator would fall back to placeholder; set FAL_KEY or OPENAI_API_KEY")
            if missing:
                issues.append("required knowledge json missing")
        passed = not missing and (not strict or not issues)
        return {
            "status": "PASS" if passed else "FAIL",
            "knowledge_files": loaded["knowledge_sources"],
            "pdf_count": len(loaded["pdf_sources_used"]),
            "knowledge_docs_count": len(loaded["knowledge_docs_used"]),
            "style_refs_count": len(loaded["style_refs_used"]),
            "missing": missing,
            "issues": issues,
            "default_writer": "full-pipeline",
            "auto_illustrator_real_available": can_auto_real,
        }

    def _select_illustrator(self, illustrator: str, allow_placeholder: bool):
        fal = bool(os.getenv("FAL_KEY", "").strip())
        openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
        if illustrator == "fal":
            return FalFluxIllustrator(), "fal-flux"
        if illustrator == "openai":
            return OpenAIImagesIllustrator(), "openai-images"
        if illustrator == "placeholder":
            if not allow_placeholder:
                raise RuntimeError("Placeholder illustrator requires --allow-placeholder.")
            return PlaceholderIllustrator(), "placeholder"
        if fal:
            return FalFluxIllustrator(), "fal-flux"
        if openai:
            return OpenAIImagesIllustrator(), "openai-images"
        if allow_placeholder:
            return PlaceholderIllustrator(), "placeholder"
        raise RuntimeError("No real illustrator configured. Set FAL_KEY or OPENAI_API_KEY, or pass --allow-placeholder.")

    def run(self, idea: str, pages: int, size: str, out_dir: str, stop_after: str | None = None, writer: str = "full-pipeline", illustrator: str = "auto", allow_placeholder: bool = False) -> Dict[str, Any]:
        out = Path(out_dir)
        images_dir = out / "images"
        out.mkdir(parents=True, exist_ok=True)

        story = StoryAgent(writer=writer).run(idea=idea, pages=pages)
        (out / "story.md").write_text(story["story_markdown"], encoding="utf-8")
        (out / "story_metadata.json").write_text(json.dumps({k: story.get(k) for k in ["knowledge_sources", "knowledge_keys_used", "knowledge_docs_used", "pdf_sources_used", "style_refs_used"]}, indent=2), encoding="utf-8")

        loaded = self.loader.load()
        directors = list(loaded["knowledge"]["directors"]["directors"].keys())
        modes = list(loaded["knowledge"]["visual_modes"]["visual_modes"].keys())
        base_prov = {
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_docs_used": loaded["knowledge_docs_used"],
            "pdf_sources_used": loaded["pdf_sources_used"],
            "style_refs_used": loaded["style_refs_used"],
        }

        style_bible = {"title": story["title"], "director_reference": directors[0], "visual_mode": modes[0], "color_notes": loaded["knowledge"]["directors"]["directors"][directors[0]]["color_palette"], "knowledge_keys_used": {"directors.directors[0]": directors[0], "visual_modes.visual_modes[0]": modes[0]}, **base_prov}
        (out / "style_bible.json").write_text(json.dumps(style_bible, indent=2), encoding="utf-8")

        page_plan = {"pages": [{"page_number": p["page_number"], "text": p["text"], "scene_description": p["scene_description"], "spread": (p["page_number"] + 1) // 2} for p in story["pages"]], "knowledge_keys_used": story["knowledge_keys_used"], **base_prov}
        (out / "page_plan.json").write_text(json.dumps(page_plan, indent=2), encoding="utf-8")

        prompts = {"prompts": [{"page_number": p["page_number"], "prompt": f"children's book illustration, {style_bible['director_reference']} inspired, {style_bible['visual_mode']}, {p['scene_description']}", "caption": p["scene_description"]} for p in story["pages"]], "knowledge_keys_used": {"style.director_reference": style_bible["director_reference"], "style.visual_mode": style_bible["visual_mode"]}, **base_prov}
        (out / "prompts.json").write_text(json.dumps(prompts, indent=2), encoding="utf-8")

        if stop_after == "style":
            return {"status": "STOPPED_AFTER_STYLE", "out_dir": str(out)}

        trim_w, trim_h = parse_trim_size(size)
        px_size = (int((trim_w + 0.25) * 300), int((trim_h + 0.25) * 300))
        illustrator_client, provider = self._select_illustrator(illustrator, allow_placeholder)
        illustrations = illustrator_client.generate(prompts["prompts"], images_dir, px_size)

        if provider == "placeholder":
            prompts["placeholder"] = True
            (out / "prompts.json").write_text(json.dumps(prompts, indent=2), encoding="utf-8")

        interior_pdf = out / "interior.pdf"
        cover_pdf = out / "cover_wrap.pdf"
        layout_meta = self.layout.render(pages=story["pages"], image_paths=illustrations["images"], output_interior=interior_pdf, output_cover=cover_pdf, size=size, include_page_numbers=False)

        preflight = self.preflight.run(interior_pdf=interior_pdf, cover_pdf=cover_pdf, image_paths=illustrations["images"], trim_size=size, bleed_in=layout_meta["bleed_in"], safe_margin_in=layout_meta["safe_margin_in"], include_page_numbers=layout_meta["page_numbers"])
        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
        return {"status": preflight["status"], "out_dir": str(out), "interior_pdf": str(interior_pdf), "cover_wrap_pdf": str(cover_pdf), "preflight_report": str(out / "preflight_report.json"), "illustrator": provider}
