from __future__ import annotations

from typing import Any, Dict

from bookforge.schemas import StoryOutput, StoryPage
from bookforge.story._vendor_fullpipeline import ChildrenStoryWriter


class FullPipelineWriter:
    """Thin wrapper around vendored Full-pipeline writer."""

    def __init__(self) -> None:
        self.writer = ChildrenStoryWriter()

    def build_story(self, idea: str, pages: int, loaded: Dict[str, Any]) -> StoryOutput:
        upstream = self.writer.generate(
            idea=idea,
            pages=pages,
            knowledge=loaded["knowledge"],
            writing_docs_text=loaded.get("writing_docs_text", ""),
            design_docs_text=loaded.get("design_docs_text", ""),
        )
        return StoryOutput(
            title=upstream["title"],
            story_markdown=upstream["story_markdown"],
            pages=[StoryPage(**p) for p in upstream["pages"]],
            knowledge_sources=loaded["knowledge_sources"],
            knowledge_keys_used=upstream.get("knowledge_keys_used", {}),
            knowledge_docs_used=loaded.get("knowledge_docs_used", []),
            pdf_sources_used=loaded.get("pdf_sources_used", []),
            style_refs_used=loaded.get("style_refs_used", []),
        )
