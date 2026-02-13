from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class StoryPageData:
    page_number: int
    text: str
    scene_description: str


class ChildrenStoryWriter:
    """Vendored full-pipeline story writer entrypoint."""

    def generate(self, idea: str, pages: int, knowledge: Dict[str, Any], writing_docs_text: str, design_docs_text: str) -> Dict[str, Any]:
        psych = knowledge["psychology"]["age_groups"].get("ages_3_5", {})
        themes = psych.get("themes", ["courage", "friendship"])
        language = psych.get("language", "Short rhythmic sentences with emotional clarity.")
        title = self._title(idea)

        beats = [
            f"{idea.title()} begins on a bright morning, full of quiet wonder.",
            f"A challenge appears: it feels big, but not impossible.",
            f"With {themes[0]}, the child tries the first brave step.",
            f"A mistake happens, then a kind friend helps adjust the plan.",
            f"Together they solve the problem and help someone else too.",
            "At bedtime, the day becomes a warm memory and a new promise.",
        ]

        pages_out: List[Dict[str, Any]] = []
        for i in range(1, pages + 1):
            beat = beats[(i - 1) * len(beats) // max(pages, 1)]
            text = f"{beat}"
            pages_out.append(
                {
                    "page_number": i,
                    "text": text,
                    "scene_description": f"Children's picture book scene, page {i}. {text}",
                }
            )

        markdown_lines = [f"# {title}", "", f"Language: {language}", ""]
        for p in pages_out:
            markdown_lines.append(f"## Page {p['page_number']}\n{p['text']}")

        return {
            "title": title,
            "story_markdown": "\n".join(markdown_lines),
            "pages": pages_out,
            "knowledge_keys_used": {
                "psychology.age_groups.ages_3_5.themes": themes,
                "psychology.age_groups.ages_3_5.language": language,
                "writing_docs_excerpt_used": writing_docs_text[:200],
                "design_docs_excerpt_used": design_docs_text[:200],
            },
        }

    def _title(self, idea: str) -> str:
        idea = idea.strip().title()
        return idea if idea.lower().startswith("the ") else f"The {idea}"
