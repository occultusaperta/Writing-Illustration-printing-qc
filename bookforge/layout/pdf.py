from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

from reportlab.lib.colors import black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def parse_trim_size(size: str) -> Tuple[float, float]:
    w, h = size.lower().split("x")
    return float(w), float(h)


class PDFLayoutEngine:
    def __init__(self, font_path: Path) -> None:
        self.font_name = "NotoSans"
        self.font_path = font_path

    def render_interior(
        self,
        pages: List[Dict[str, Any]],
        image_paths: List[str],
        output_interior: Path,
        size: str,
        bleed_in: float,
        safe_margin_in: float,
    ) -> Dict[str, Any]:
        trim_w, trim_h = parse_trim_size(size)
        page_w = (trim_w + bleed_in * 2) * 72
        page_h = (trim_h + bleed_in * 2) * 72
        pdfmetrics.registerFont(TTFont(self.font_name, str(self.font_path)))

        c = canvas.Canvas(str(output_interior), pagesize=(page_w, page_h), pageCompression=0)
        c.setAuthor("KDP Premium Studio")
        c.setTitle("Interior")

        safe_x = (bleed_in + safe_margin_in) * 72
        safe_y = (bleed_in + safe_margin_in) * 72
        safe_w = (trim_w - 2 * safe_margin_in) * 72
        safe_h = (trim_h - 2 * safe_margin_in) * 72

        for page, img_path in zip(pages, image_paths):
            img = ImageReader(img_path)
            c.drawImage(img, 0, 0, page_w, page_h, preserveAspectRatio=True, anchor="c")

            panel_h = min(140, safe_h * 0.35)
            panel_y = safe_y
            c.setFillColorRGB(1, 1, 1, alpha=0.88)
            c.roundRect(safe_x, panel_y, safe_w, panel_h, 10, stroke=0, fill=1)
            c.setFillColor(black)

            font_size = 20
            leading = 1.25
            wrapped: List[str] = []
            raw_text = page["text"].strip()
            while font_size >= 10:
                max_chars = max(20, int(safe_w / (font_size * 0.45)))
                wrapped = textwrap.wrap(raw_text, width=max_chars)
                if len(wrapped) * (font_size * leading) <= panel_h - 18:
                    break
                font_size -= 1
            if font_size < 10:
                raise RuntimeError(f"Text overflow could not be resolved on page {page['page_number']}.")

            c.setFont(self.font_name, font_size)
            text_y = panel_y + panel_h - (font_size + 10)
            for line in wrapped:
                c.drawString(safe_x + 12, text_y, line)
                text_y -= font_size * leading
            c.showPage()

        c.save()
        return {"page_dimensions_pt": [page_w, page_h]}

    def render_cover_wrap(
        self,
        output_cover: Path,
        output_guides: Path,
        trim_w: float,
        trim_h: float,
        bleed_in: float,
        safe_margin_in: float,
        page_count: int,
        spine_w: float,
    ) -> Dict[str, Any]:
        cover_w = 2 * trim_w + spine_w + 2 * bleed_in
        cover_h = trim_h + 2 * bleed_in
        w_pt = cover_w * 72
        h_pt = cover_h * 72

        c = canvas.Canvas(str(output_cover), pagesize=(w_pt, h_pt), pageCompression=0)
        c.setTitle("Cover Wrap")
        c.setFont(self.font_name, 18)
        c.drawString((trim_w + bleed_in + spine_w) * 72 + 24, h_pt - 56, "Front Cover")
        c.drawString(24, h_pt - 56, "Back Cover")
        barcode_w, barcode_h = 2.0 * 72, 1.2 * 72
        c.setFillColor(white)
        c.rect(bleed_in * 72 + 24, bleed_in * 72 + 24, barcode_w, barcode_h, stroke=0, fill=1)
        c.setFillColor(black)
        c.save()

        g = canvas.Canvas(str(output_guides), pagesize=(w_pt, h_pt), pageCompression=0)
        g.setTitle("Cover Guides")
        g.rect(bleed_in * 72, bleed_in * 72, (2 * trim_w + spine_w) * 72, trim_h * 72)
        g.rect((bleed_in + safe_margin_in) * 72, (bleed_in + safe_margin_in) * 72, (2 * trim_w + spine_w - 2 * safe_margin_in) * 72, (trim_h - 2 * safe_margin_in) * 72)
        g.line((bleed_in + trim_w) * 72, bleed_in * 72, (bleed_in + trim_w) * 72, (bleed_in + trim_h) * 72)
        g.line((bleed_in + trim_w + spine_w) * 72, bleed_in * 72, (bleed_in + trim_w + spine_w) * 72, (bleed_in + trim_h) * 72)
        g.save()

        return {"cover_w_in": cover_w, "cover_h_in": cover_h}
