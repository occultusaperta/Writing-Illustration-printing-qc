from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from bookforge.illustration.fal_flux import FalFluxIllustrator
from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.layout.pdf import PDFLayoutEngine, parse_trim_size
from bookforge.qc.kdp_preflight import KDPPreflight
from bookforge.story.agent import StoryAgent


class BookforgePipeline:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()
        self.story = StoryAgent()
        self.illustrator = FalFluxIllustrator()
        self.layout = PDFLayoutEngine()
        self.preflight = KDPPreflight()

    def doctor(self) -> Dict[str, Any]:
        loaded = self.loader.load()
        required = [Path(self.loader.knowledge_root / p) for p in self.loader.REQUIRED_JSON]
        missing = [str(p) for p in required if not p.exists()]
        passed = not missing
        return {
            "status": "PASS" if passed else "FAIL",
            "knowledge_files": loaded["knowledge_sources"],
            "pdf_count": len(loaded["pdf_sources_used"]),
            "style_refs_count": loaded["style_refs_count"],
            "missing": missing,
        }

    def run(self, idea: str, pages: int, size: str, out_dir: str, stop_after: str | None = None) -> Dict[str, Any]:
        out = Path(out_dir)
        images_dir = out / "images"
        out.mkdir(parents=True, exist_ok=True)

        story = self.story.run(idea=idea, pages=pages)
        (out / "story.md").write_text(story["story_markdown"], encoding="utf-8")

        loaded = self.loader.load()
        directors = list(loaded["knowledge"]["directors"]["directors"].keys())
        modes = list(loaded["knowledge"]["visual_modes"]["visual_modes"].keys())
        style_bible = {
            "title": story["title"],
            "director_reference": directors[0],
            "visual_mode": modes[0],
            "color_notes": loaded["knowledge"]["directors"]["directors"][directors[0]]["color_palette"],
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {
                "directors.directors[0]": directors[0],
                "visual_modes.visual_modes[0]": modes[0],
            },
            "pdf_sources_used": loaded["pdf_sources_used"],
            "sample_spreads": [
                {"spread": 1, "left_page": 2, "right_page": 3, "note": "intro mood"},
                {"spread": 2, "left_page": 4, "right_page": 5, "note": "conflict mood"},
            ],
        }
        (out / "style_bible.json").write_text(json.dumps(style_bible, indent=2), encoding="utf-8")

        page_plan = {
            "pages": [
                {
                    "page_number": p["page_number"],
                    "text": p["text"],
                    "scene_description": p["scene_description"],
                    "spread": (p["page_number"] + 1) // 2,
                }
                for p in story["pages"]
            ],
            "knowledge_sources": story["knowledge_sources"],
            "knowledge_keys_used": story["knowledge_keys_used"],
            "pdf_sources_used": story["pdf_sources_used"],
        }
        (out / "page_plan.json").write_text(json.dumps(page_plan, indent=2), encoding="utf-8")

        prompts = {
            "prompts": [
                {
                    "page_number": p["page_number"],
                    "prompt": f"children's book illustration, {style_bible['director_reference']} inspired, {style_bible['visual_mode']}, {p['scene_description']}",
                    "caption": p["scene_description"],
                }
                for p in story["pages"]
            ],
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {
                "style.director_reference": style_bible["director_reference"],
                "style.visual_mode": style_bible["visual_mode"],
            },
            "pdf_sources_used": loaded["pdf_sources_used"],
        }
        (out / "prompts.json").write_text(json.dumps(prompts, indent=2), encoding="utf-8")

        if stop_after == "style":
            return {"status": "STOPPED_AFTER_STYLE", "out_dir": str(out)}

        trim_w, trim_h = parse_trim_size(size)
        px_size = (int((trim_w + 0.25) * 300), int((trim_h + 0.25) * 300))
        illustrations = self.illustrator.generate(prompts["prompts"], images_dir, px_size)

        interior_pdf = out / "interior.pdf"
        cover_pdf = out / "cover_wrap.pdf"
        layout_meta = self.layout.render(
            pages=story["pages"],
            image_paths=illustrations["images"],
            output_interior=interior_pdf,
            output_cover=cover_pdf,
            size=size,
            include_page_numbers=False,
        )

        preflight = self.preflight.run(
            interior_pdf=interior_pdf,
            cover_pdf=cover_pdf,
            image_paths=illustrations["images"],
            trim_size=size,
            bleed_in=layout_meta["bleed_in"],
            safe_margin_in=layout_meta["safe_margin_in"],
            include_page_numbers=layout_meta["page_numbers"],
        )

        (out / "preflight_report.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
        return {
            "status": preflight["status"],
            "out_dir": str(out),
            "interior_pdf": str(interior_pdf),
            "cover_wrap_pdf": str(cover_pdf),
            "preflight_report": str(out / "preflight_report.json"),
        }
