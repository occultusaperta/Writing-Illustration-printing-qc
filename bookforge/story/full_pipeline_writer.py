from __future__ import annotations

from typing import Any, Dict

from bookforge.schemas import StoryOutput, StoryPage
from bookforge.story._vendor_fullpipeline import generate_story


class FullPipelineWriter:
    """Thin wrapper around vendored Full-pipeline writer code."""

    def build_story(self, idea: str, pages: int, loaded: Dict[str, Any]) -> StoryOutput:
        knowledge = loaded["knowledge"]
        docs_text_parts = [loaded.get("writing_docs_text", ""), loaded.get("design_docs_text", "")]
        docs_text = "\n\n".join(p for p in docs_text_parts if p).strip() or None

        story_md, page_plan = generate_story(idea=idea, pages=pages, knowledge=knowledge, docs_text=docs_text)
        story_pages = [
            StoryPage(
                page_number=page["page_number"],
                text=page["text"],
                scene_description=page["scene_description"],
            )
            for page in page_plan["pages"]
        ]

        keys_used = {
            "psychology.age_groups.ages_3_5.themes[0]": knowledge["psychology"]["age_groups"]["ages_3_5"]["themes"][0],
            "directors.directors": list(knowledge["directors"]["directors"].keys())[:3],
            "visual_modes.visual_modes": list(knowledge["visual_modes"]["visual_modes"].keys())[:3],
        }

        return StoryOutput(
            title=page_plan["title"],
            story_markdown=story_md,
            pages=story_pages,
            knowledge_sources=loaded["knowledge_sources"],
            knowledge_keys_used=keys_used,
            pdf_sources_used=loaded["pdf_sources_used"],
            knowledge_docs_used=loaded["knowledge_docs_used"],
            style_refs_used=loaded["style_refs_used"],
        )
