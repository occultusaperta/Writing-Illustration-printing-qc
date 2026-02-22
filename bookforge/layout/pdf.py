from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageFilter
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
        try:
            pdfmetrics.registerFont(TTFont(self.font_name, str(self.font_path)))
        except Exception as exc:
            raise RuntimeError("Font embed failed. Ensure assets/fonts/NotoSans-Regular.ttf exists and is a valid TTF.") from exc

    def render_interior(self, pages: List[Dict[str, Any]], image_paths: List[str], output_interior: Path, size: str, bleed_in: float, safe_margin_in: float, layout_preset: Dict[str, Any], typography_preset: Dict[str, Any]) -> Dict[str, Any]:
        trim_w, trim_h = parse_trim_size(size)
        page_w = (trim_w + bleed_in * 2) * 72
        page_h = (trim_h + bleed_in * 2) * 72
        c = canvas.Canvas(str(output_interior), pagesize=(page_w, page_h), pageCompression=0)
        safe_x = (bleed_in + safe_margin_in) * 72
        safe_y = (bleed_in + safe_margin_in) * 72
        safe_w = (trim_w - 2 * safe_margin_in) * 72
        safe_h = (trim_h - 2 * safe_margin_in) * 72

        for page, img_path in zip(pages, image_paths):
            c.drawImage(ImageReader(img_path), 0, 0, page_w, page_h, preserveAspectRatio=True, anchor="c")
            panel_h = safe_h * layout_preset["panel_height_ratio"]
            panel_y = safe_y if layout_preset["panel_position"] == "bottom" else safe_y + safe_h - panel_h
            c.setFillColorRGB(1, 1, 1)
            c.roundRect(safe_x, panel_y, safe_w, panel_h, 8, stroke=0, fill=1)
            c.setFillColor(black)

            raw_text = page["text"].strip()
            font_size = typography_preset["base_font_size"]
            wrapped: List[str] = []
            while font_size >= typography_preset["min_font_size"]:
                max_chars = max(14, int((safe_w - 2 * layout_preset["panel_padding_pt"]) / (font_size * 0.50)))
                wrapped = textwrap.wrap(raw_text, width=max_chars)
                line_h = font_size * typography_preset["leading"]
                if len(wrapped) <= typography_preset["max_lines"] and len(wrapped) * line_h <= panel_h - 2 * layout_preset["panel_padding_pt"]:
                    break
                font_size -= 1
            if font_size < typography_preset["min_font_size"]:
                raise RuntimeError(f"Text overflow could not be resolved on page {page['page_number']}. Reduce text or choose a larger panel preset.")

            c.setFont(self.font_name, font_size)
            y = panel_y + panel_h - layout_preset["panel_padding_pt"] - font_size
            for line in wrapped:
                if layout_preset["text_align"] == "center":
                    c.drawCentredString(safe_x + safe_w / 2, y, line)
                else:
                    c.drawString(safe_x + layout_preset["panel_padding_pt"], y, line)
                y -= font_size * typography_preset["leading"]
            if layout_preset["show_page_numbers"]:
                c.setFont(self.font_name, 9)
                c.drawRightString(page_w - safe_x, safe_y - 14, str(page["page_number"]))
            c.showPage()
        c.save()
        return {"page_dimensions_pt": [page_w, page_h]}

    def render_cover_wrap(self, output_cover: Path, output_guides: Path, trim_w: float, trim_h: float, bleed_in: float, safe_margin_in: float, page_count: int, spine_w: float, title: str, author: str, approved_cover: Path, approved_style: Path, cover_preset: Dict[str, Any], cover_config: Dict[str, Any]) -> Dict[str, Any]:
        cover_w = 2 * trim_w + spine_w + 2 * bleed_in
        cover_h = trim_h + 2 * bleed_in
        w_pt, h_pt = cover_w * 72, cover_h * 72
        c = canvas.Canvas(str(output_cover), pagesize=(w_pt, h_pt), pageCompression=0)

        back_x = bleed_in * 72
        spine_x = (bleed_in + trim_w) * 72
        front_x = (bleed_in + trim_w + spine_w) * 72
        panel_y = bleed_in * 72
        panel_h = trim_h * 72

        if cover_preset["back_background_mode"] == "style_blur" and approved_style.exists():
            with Image.open(approved_style) as im:
                blur = im.convert("RGB").filter(ImageFilter.GaussianBlur(radius=6))
                tmp = output_cover.parent / ".tmp_style_blur.jpg"
                blur.save(tmp)
                c.drawImage(ImageReader(str(tmp)), 0, 0, w_pt, h_pt, preserveAspectRatio=True, anchor="c")
                tmp.unlink(missing_ok=True)
        else:
            c.setFillColorRGB(0.94, 0.93, 0.9)
            c.rect(0, 0, w_pt, h_pt, stroke=0, fill=1)

        c.drawImage(ImageReader(str(approved_cover)), front_x, 0, (trim_w + bleed_in) * 72, h_pt, preserveAspectRatio=True, anchor="c")
        c.setFillColor(black)
        if cover_preset["title_placement"] == "front_top":
            c.setFont(self.font_name, 30)
            c.drawCentredString(front_x + trim_w * 36, panel_y + panel_h - 50, title)
        elif cover_preset["title_placement"] == "front_bottom":
            c.setFont(self.font_name, 30)
            c.drawCentredString(front_x + trim_w * 36, panel_y + 42, title)
        else:
            c.setFont(self.font_name, 30)
            c.drawCentredString(front_x + trim_w * 36, panel_y + panel_h / 2, title)

        c.setFont(self.font_name, 14)
        c.drawCentredString(front_x + trim_w * 36, panel_y + 20 if cover_preset["author_placement"] == "front_bottom" else panel_y + panel_h - 78, author)
        if spine_w >= cover_config["spine_text_min_in"]:
            c.saveState()
            c.translate(spine_x + (spine_w * 72) / 2, panel_y + panel_h / 2)
            c.rotate(90)
            c.setFont(self.font_name, 12)
            c.drawCentredString(0, 0, title)
            c.restoreState()

        bx, by, bw, bh = cover_preset["barcode_box_in"]
        c.setFillColor(white)
        c.rect(back_x + bx * 72, panel_y + by * 72, bw * 72, bh * 72, stroke=0, fill=1)
        c.save()

        g = canvas.Canvas(str(output_guides), pagesize=(w_pt, h_pt), pageCompression=0)
        g.rect(back_x, panel_y, (2 * trim_w + spine_w) * 72, panel_h)
        g.rect((bleed_in + safe_margin_in) * 72, (bleed_in + safe_margin_in) * 72, (2 * trim_w + spine_w - 2 * safe_margin_in) * 72, (trim_h - 2 * safe_margin_in) * 72)
        g.line(spine_x, panel_y, spine_x, panel_y + panel_h)
        g.line(front_x, panel_y, front_x, panel_y + panel_h)
        g.save()
        return {
            "cover_w_in": cover_w,
            "cover_h_in": cover_h,
            "back_background_rect_pt": [0, 0, w_pt, h_pt],
            "front_art_rect_pt": [front_x, 0, (trim_w + bleed_in) * 72, h_pt],
            "spine_rect_pt": [spine_x, panel_y, spine_w * 72, panel_h],
        }

    def render_interior_preview(self, out_pdf: Path, size: str, bleed_in: float, safe_margin_in: float, preset: Any) -> None:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        dummy = out_pdf.parent / ".preview.png"
        Image.new("RGB", (1200, 1200), (205, 220, 230)).save(dummy)
        self.render_interior([{"page_number": 1, "text": f"Sample text for {preset.name}."}], [str(dummy)], out_pdf, size, bleed_in, safe_margin_in, preset.__dict__, {"base_font_size": 18, "min_font_size": 12, "leading": 1.25, "max_lines": 8})
        dummy.unlink(missing_ok=True)

    def render_cover_preview(self, out_pdf: Path, trim_w: float, trim_h: float, bleed_in: float, safe_margin_in: float, preset: Any) -> None:
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        dummy = out_pdf.parent / ".cover.png"
        style = out_pdf.parent / ".style.png"
        Image.new("RGB", (1200, 1200), (180, 170, 200)).save(dummy)
        Image.new("RGB", (1200, 1200), (170, 200, 190)).save(style)
        self.render_cover_wrap(out_pdf, out_pdf.with_name(out_pdf.stem + "_guides.pdf"), trim_w, trim_h, bleed_in, safe_margin_in, 24, 0.2, "Sample Title", "Sample Author", dummy, style, preset.__dict__, {"spine_text_min_in": 0.1})
        style.unlink(missing_ok=True)
        dummy.unlink(missing_ok=True)
