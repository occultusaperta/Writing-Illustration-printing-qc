from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from bookforge.knowledge.loader import KnowledgeLoader


def parse_trim_size(size: str) -> Tuple[float, float]:
    w, h = size.lower().split("x")
    return float(w), float(h)


class PDFLayoutEngine:
    def __init__(self) -> None:
        self.loader = KnowledgeLoader()

    def render(
        self,
        pages: List[Dict[str, Any]],
        image_paths: List[str],
        output_interior: Path,
        output_cover: Path,
        size: str,
        include_page_numbers: bool = False,
    ) -> Dict[str, Any]:
        loaded = self.loader.load()
        trim_w, trim_h = parse_trim_size(size)
        bleed = 0.125
        safe_margin = 0.375
        page_w = (trim_w + bleed * 2) * 72
        page_h = (trim_h + bleed * 2) * 72

        c = canvas.Canvas(str(output_interior), pagesize=(page_w, page_h), pageCompression=0)
        c.setAuthor("bookforge")
        c.setTitle("BookForge Interior")
        c.setSubject("KDP-ready interior")

        for i, (page, img_path) in enumerate(zip(pages, image_paths), start=1):
            x = safe_margin * 72
            y = safe_margin * 72
            w = page_w - 2 * safe_margin * 72
            h = page_h - 2 * safe_margin * 72 - 70
            img = ImageReader(img_path)
            c.drawImage(img, x, y + 70, w, h, preserveAspectRatio=True, anchor='c')
            c.setFont("Times-Roman", 12)
            c.drawString(x, y + 48, page["text"][:130])
            if include_page_numbers:
                c.setFont("Times-Roman", 10)
                c.drawRightString(page_w - x, y + 20, str(i))
            c.showPage()
        c.save()

        cover_w = (trim_w * 2 + 0.25) * 72  # placeholder spine area
        cover_h = (trim_h + bleed * 2) * 72
        cc = canvas.Canvas(str(output_cover), pagesize=(cover_w, cover_h), pageCompression=0)
        cc.setTitle("BookForge Cover Wrap")
        cc.setFont("Times-Roman", 24)
        cc.drawString(72, cover_h - 96, "Placeholder Cover Wrap")
        cc.setFont("Times-Roman", 12)
        cc.drawString(72, cover_h - 120, "Front + Back + Placeholder Spine")
        cc.rect(36, 36, cover_w - 72, cover_h - 72)
        cc.save()

        return {
            "trim_size": size,
            "bleed_in": bleed,
            "safe_margin_in": safe_margin,
            "page_dimensions_pt": [page_w, page_h],
            "page_numbers": include_page_numbers,
            "knowledge_sources": loaded["knowledge_sources"],
            "knowledge_keys_used": {"layout.font": "Times-Roman"},
            "pdf_sources_used": loaded["pdf_sources_used"],
        }
