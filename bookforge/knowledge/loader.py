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
        self.writing_txt_root = self.pdf_root / "writing_txt"
        self.design_txt_root = self.pdf_root / "design_txt"
        self.style_refs_root = self.knowledge_root / "style_refs"

    def _collect_docs(self, root: Path) -> List[Path]:
        if not root.exists():
            return []
        docs: List[Path] = []
        for ext in ("*.txt", "*.md"):
            docs.extend(p for p in root.rglob(ext) if p.is_file())
        return sorted(set(docs))

    def _read_docs_text(self, docs: List[Path]) -> str:
        chunks: List[str] = []
        for path in docs:
            rel = str(path.relative_to(self.repo_root))
            text = path.read_text(encoding="utf-8")
            chunks.append(f"\n\n--- {rel} ---\n{text}")
        return "".join(chunks).strip()

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

        pdf_sources = sorted(str(p.relative_to(self.repo_root)) for p in self.pdf_root.glob("*.pdf") if p.is_file())

        writing_docs = self._collect_docs(self.writing_txt_root)
        design_docs = self._collect_docs(self.design_txt_root)
        all_docs = sorted({str(p.relative_to(self.repo_root)) for p in writing_docs + design_docs})

        style_refs_used = 0
        if self.style_refs_root.exists():
            image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
            style_refs_used = sum(1 for p in self.style_refs_root.rglob("*") if p.is_file() and p.suffix.lower() in image_exts)

        return {
            "knowledge": data,
            "knowledge_sources": sources,
            "pdf_sources_used": pdf_sources,
            "knowledge_docs_used": all_docs,
            "writing_docs_text": self._read_docs_text(writing_docs),
            "design_docs_text": self._read_docs_text(design_docs),
            "style_refs_used": style_refs_used,
            "style_refs_count": style_refs_used,
        }
