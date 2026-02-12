from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class KnowledgeLoader:
    """Always loads required knowledge files from repository root knowledge/."""

    REQUIRED_JSON = ["directors.json", "visual_modes.json", "psychology.json"]

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.knowledge_root = self.repo_root / "knowledge"
        self.pdf_root = self.knowledge_root / "pdfs"

    def load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        sources: List[str] = []
        for name in self.REQUIRED_JSON:
            path = self.knowledge_root / name
            if not path.exists():
                raise FileNotFoundError(f"Missing required knowledge file: {path}")
            with path.open("r", encoding="utf-8") as f:
                data[name.replace(".json", "")] = json.load(f)
            sources.append(str(path.relative_to(self.repo_root)))

        pdf_sources = sorted(
            str(p.relative_to(self.repo_root))
            for p in self.pdf_root.glob("*.pdf")
            if p.is_file()
        )

        style_refs_count = len(data.get("directors", {}).get("directors", {})) + len(
            data.get("visual_modes", {}).get("visual_modes", {})
        )

        return {
            "knowledge": data,
            "knowledge_sources": sources,
            "pdf_sources_used": pdf_sources,
            "style_refs_count": style_refs_count,
        }
