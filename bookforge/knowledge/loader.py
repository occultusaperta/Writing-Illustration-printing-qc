from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class KnowledgeLoader:
    REQUIRED_JSON = ["directors.json", "visual_modes.json", "psychology.json"]

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.knowledge_root = self.repo_root / "knowledge"
        self.docs_root = self.knowledge_root / "docs"
        self.pdf_root = self.knowledge_root / "pdfs"
        self.style_refs_root = self.knowledge_root / "style_refs"

    def load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        knowledge_sources: List[str] = []
        for name in self.REQUIRED_JSON:
            path = self.knowledge_root / name
            if not path.exists():
                raise FileNotFoundError(f"Missing required knowledge file: {path}")
            data[name.replace(".json", "")] = json.loads(path.read_text(encoding="utf-8"))
            knowledge_sources.append(str(path.relative_to(self.repo_root)))

        docs_texts: List[str] = []
        docs_sources: List[str] = []
        for ext in ("*.txt", "*.md"):
            for p in sorted(self.docs_root.rglob(ext)) if self.docs_root.exists() else []:
                docs_sources.append(str(p.relative_to(self.repo_root)))
                docs_texts.append(p.read_text(encoding="utf-8", errors="ignore"))

        pdf_sources = sorted(str(p.relative_to(self.repo_root)) for p in self.pdf_root.rglob("*.pdf")) if self.pdf_root.exists() else []

        style_refs_used: List[str] = []
        if self.style_refs_root.exists():
            image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
            style_refs_used = sorted(
                str(p.relative_to(self.repo_root))
                for p in self.style_refs_root.rglob("*")
                if p.is_file() and p.suffix.lower() in image_exts
            )

        writing_docs_text = "\n\n".join(t for s, t in zip(docs_sources, docs_texts) if "writing" in s.lower())
        design_docs_text = "\n\n".join(t for s, t in zip(docs_sources, docs_texts) if "design" in s.lower() or "visual" in s.lower())

        return {
            "knowledge": data,
            "knowledge_sources": knowledge_sources,
            "knowledge_docs_used": docs_sources,
            "pdf_sources_used": pdf_sources,
            "style_refs_used": style_refs_used,
            "writing_docs_text": writing_docs_text,
            "design_docs_text": design_docs_text,
        }
