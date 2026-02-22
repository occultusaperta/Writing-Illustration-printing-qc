from __future__ import annotations

from typing import Any, Dict, List

from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.schemas import StoryOutput, StoryPage
from bookforge.story.full_pipeline_writer import FullPipelineWriter


class TemplateStoryWriter:
    """Simple deterministic template writer fallback."""

    def build_story(self, idea: str, pages: int, loaded: Dict[str, Any]) -> StoryOutput:
        knowledge = loaded["knowledge"]
        age_defaults = knowledge["psychology"]["age_groups"]["ages_3_5"]
        theme = age_defaults["themes"][0]
        title = f"The Wonderful {idea.title()}"

        story_pages: List[StoryPage] = []
        beats = self._beats(idea, pages)
        for idx, beat in enumerate(beats, start=1):
            story_pages.append(
                StoryPage(
                    page_number=idx,
                    text=beat,
                    scene_description=f"Illustration: {beat}",
                )
            )

        markdown = "\n".join([f"# {title}", "", f"Theme: {theme}", ""] + [f"## Page {p.page_number}\n{p.text}" for p in story_pages])

        return StoryOutput(
            title=title,
            story_markdown=markdown,
            pages=story_pages,
            knowledge_sources=loaded["knowledge_sources"],
            knowledge_keys_used={
                "psychology.age_groups.ages_3_5.themes[0]": theme,
                "directors.directors": list(knowledge["directors"]["directors"].keys())[:2],
            },
            pdf_sources_used=loaded["pdf_sources_used"],
            knowledge_docs_used=loaded["knowledge_docs_used"],
            style_refs_used=loaded.get("style_refs_used", []),
        )

    def _beats(self, idea: str, pages: int) -> List[str]:
        arc = [
            f"{idea.title()} wakes up excited for a new day.",
            "A tiny problem appears and feels a little scary.",
            "A friend offers help and a brave plan.",
            "They try once, learn, and try again.",
            "Kindness and teamwork solve the problem.",
            "Everyone celebrates and rests happily.",
        ]
        return [arc[i % len(arc)] for i in range(pages)]


class StoryAgent:
    def __init__(self, writer: str = "full-pipeline") -> None:
        self.loader = KnowledgeLoader()
        self.writer_name = writer
        self.template_writer = TemplateStoryWriter()
        self.full_pipeline_writer = FullPipelineWriter()

    def run(self, idea: str, pages: int) -> Dict[str, Any]:
        loaded = self.loader.load()

        if self.writer_name == "template":
            output = self.template_writer.build_story(idea=idea, pages=pages, loaded=loaded)
        else:
            output = self.full_pipeline_writer.build_story(idea=idea, pages=pages, loaded=loaded)

        return output.to_dict()
