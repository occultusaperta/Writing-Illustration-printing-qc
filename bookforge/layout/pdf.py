from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from bookforge.knowledge.loader import KnowledgeLoader


def parse_trim_size(size: str) -> Tuple[float, float]:
    w, h = size.lower().split("x")
    return float(w), float(h)


class PDFLayoutEngine:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()
        self.font_name = "NotoSans"
        self.font_path = self.loader.repo_root / "assets" / "fonts" / "NotoSans-Regular.ttf"

    def render(self, pages: List[Dict[str, Any]], image_paths: List[str], output_interior: Path, output_cover: Path, size: str, include_page_numbers: bool = False) -> Dict[str, Any]:
        loaded = self.loader.load()
        trim_w, trim_h = parse_trim_size(size)
        bleed = 0.125
        safe_margin = 0.375
        page_w = (trim_w + bleed * 2) * 72
        page_h = (trim_h + bleed * 2) * 72

        if self.font_path.exists():
            pdfmetrics.registerFont(TTFont(self.font_name, str(self.font_path)))

        c = canvas.Canvas(str(output_interior), pagesize=(page_w, page_h), pageCompression=0)
        c.setAuthor("bookforge")
        c.setTitle("BookForge Interior")

        safe_x = bleed * 72 + safe_margin * 72
        safe_y = bleed * 72 + safe_margin * 72
        safe_w = trim_w * 72 - 2 * safe_margin * 72
        safe_h = trim_h * 72 - 2 * safe_margin * 72

        for i, (page, img_path) in enumerate(zip(pages, image_paths), start=1):
            img = ImageReader(img_path)
            c.drawImage(img, safe_x, safe_y + 56, safe_w, safe_h - 56, preserveAspectRatio=True, anchor="c")
            c.setFont(self.font_name if self.font_path.exists() else "Times-Roman", 12)
            c.drawString(safe_x, safe_y + 36, page["text"][:130])
            if include_page_numbers:
                c.setFont(self.font_name if self.font_path.exists() else "Times-Roman", 10)
                c.drawRightString(page_w - safe_x, safe_y + 14, str(i))
            c.showPage()
        c.save()

        cover_w = (trim_w * 2 + 0.25 + bleed * 2) * 72
        cover_h = (trim_h + bleed * 2) * 72
        cc = canvas.Canvas(str(output_cover), pagesize=(cover_w, cover_h), pageCompression=0)
        cc.setFont(self.font_name if self.font_path.exists() else "Times-Roman", 24)
        cc.drawString(72, cover_h - 96, "BookForge Cover Wrap")
        cc.setFont(self.font_name if self.font_path.exists() else "Times-Roman", 12)
        cc.drawString(72, cover_h - 120, "Front + Back + spine area")
        cc.rect(36, 36, cover_w - 72, cover_h - 72)
        cc.save()

        return {
            "trim_size": size,
            "bleed_in": bleed,
            "safe_margin_in": safe_margin,
            "page_dimensions_pt": [page_w, page_h],
            "page_numbers": include_page_numbers,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_docs_used": loaded["knowledge_docs_used"],
            "pdf_sources_used": loaded["pdf_sources_used"],
            "style_refs_used": loaded["style_refs_used"],
            "knowledge_keys_used": {"layout.font": self.font_name, "layout.font_path": str(self.font_path.relative_to(self.loader.repo_root))},
        }
