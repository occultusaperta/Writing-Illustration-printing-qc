from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class Provenance:
    knowledge_sources: List[str] = field(default_factory=list)
    knowledge_keys_used: Dict[str, Any] = field(default_factory=dict)
    pdf_sources_used: List[str] = field(default_factory=list)
    knowledge_docs_used: List[str] = field(default_factory=list)
    style_refs_used: int = 0


@dataclass
class StoryPage:
    page_number: int
    text: str
    scene_description: str


@dataclass
class StoryOutput(Provenance):
    title: str = ""
    story_markdown: str = ""
    pages: List[StoryPage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pages"] = [asdict(p) for p in self.pages]
        return d
