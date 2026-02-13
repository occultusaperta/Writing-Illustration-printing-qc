from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class _StoryArc:
    hook: str
    challenge: str
    escalation: str
    turn: str
    resolution: str
    reflection: str


class FullPipelineWritingAgent:
    """Vendored writer implementation used by BookForge."""

    def generate_story(self, idea: str, pages: int, knowledge: Dict[str, Any], docs_text: str | None = None) -> Tuple[str, Dict[str, Any]]:
        psych = knowledge["psychology"]["age_groups"]["ages_3_5"]
        theme = psych["themes"][0]
        language_notes = psych.get("language", "short rhythmic sentences")
        title = self._title_from_idea(idea)

        arc = self._build_arc(idea, theme)
        page_text = self._expand_arc_to_pages(arc=arc, pages=pages)
        page_plan = {
            "title": title,
            "pages": [
                {
                    "page_number": i + 1,
                    "text": text,
                    "scene_description": f"{idea.title()} story illustration, page {i + 1}: {text}",
                }
                for i, text in enumerate(page_text)
            ],
        }

        markdown_sections: List[str] = [
            f"# {title}",
            "",
            f"Theme: {theme}",
            f"Language note: {language_notes}",
            "",
        ]
        for page in page_plan["pages"]:
            markdown_sections.append(f"## Page {page['page_number']}\n{page['text']}")

        return "\n".join(markdown_sections), page_plan

    def _title_from_idea(self, idea: str) -> str:
        core = idea.strip().capitalize()
        if not core.lower().startswith("the "):
            core = f"The {core}"
        return core

    def _build_arc(self, idea: str, theme: str) -> _StoryArc:
        lead = idea.strip().rstrip(".")
        return _StoryArc(
            hook=f"{lead} starts with a tiny glow and an even tinier voice.",
            challenge="A dark path appears, and fear whispers to turn back.",
            escalation=f"Each step shakes, but a friend reminds them that {theme} grows when shared.",
            turn="They breathe deep, ask for help, and try one brave step at a time.",
            resolution="The path lights up, and everyone can finally find their way home.",
            reflection="That night, the glow is brighter, because courage can begin quietly.",
        )

    def _expand_arc_to_pages(self, arc: _StoryArc, pages: int) -> List[str]:
        beats = [arc.hook, arc.challenge, arc.escalation, arc.turn, arc.resolution, arc.reflection]
        chunks: List[str] = []
        for i in range(pages):
            beat = beats[i * len(beats) // max(pages, 1)]
            suffix = self._suffix_for_index(i, pages)
            chunks.append(f"{beat} {suffix}".strip())
        return chunks

    def _suffix_for_index(self, idx: int, pages: int) -> str:
        position = idx + 1
        if position == 1:
            return "Morning begins softly."
        if position == pages:
            return "The end feels warm and hopeful."
        if position % 2 == 0:
            return "A gentle rhythm carries the scene forward."
        return "A small choice changes what happens next."


def generate_story(idea: str, pages: int, knowledge: Dict[str, Any], docs_text: str | None = None) -> Tuple[str, Dict[str, Any]]:
    return FullPipelineWritingAgent().generate_story(idea=idea, pages=pages, knowledge=knowledge, docs_text=docs_text)
