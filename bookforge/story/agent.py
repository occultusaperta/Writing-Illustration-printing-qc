from __future__ import annotations

from typing import Any, Dict, List

from bookforge.knowledge.loader import KnowledgeLoader
from bookforge.schemas import StoryOutput, StoryPage


class StoryAgent:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def run(self, idea: str, pages: int) -> Dict[str, Any]:
        loaded = self.loader.load()
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

        markdown = "\n".join([f"# {title}", "", f"Theme: {theme}", ""] + [
            f"## Page {p.page_number}\n{p.text}" for p in story_pages
        ])

        output = StoryOutput(
            title=title,
            story_markdown=markdown,
            pages=story_pages,
            knowledge_sources=loaded["knowledge_sources"],
            knowledge_keys_used={
                "psychology.age_groups.ages_3_5.themes[0]": theme,
                "directors.directors": list(knowledge["directors"]["directors"].keys())[:2],
            },
            pdf_sources_used=loaded["pdf_sources_used"],
        )
        return output.to_dict()

    def _beats(self, idea: str, pages: int) -> List[str]:
        arc = [
            f"{idea.title()} wakes up excited for a new day.",
            "A tiny problem appears and feels a little scary.",
            "A friend offers help and a brave plan.",
            "They try once, learn, and try again.",
            "Kindness and teamwork solve the problem.",
            "Everyone celebrates and rests happily.",
        ]
        result = []
        for i in range(pages):
            result.append(arc[i % len(arc)])
        return result
