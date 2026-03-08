from __future__ import annotations

from pathlib import Path
import re
import tempfile

import numpy as np
from typing import Any, Dict, List, Tuple

from bookforge.typography import PageTypographyPlan
from bookforge.typography.rendering import draw_typography_plan

from PIL import Image, ImageFilter
from reportlab.lib.colors import black, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

try:
    import pyphen
except Exception:  # optional runtime dependency in some environments
    pyphen = None




def extract_typography_directives(markdown_text: str) -> List[Dict[str, Any]]:
    directives: List[Dict[str, Any]] = []
    for line in markdown_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            content = raw.lstrip("#").strip()
            if content:
                directives.append({"kind": "headline", "text": content})
        spaced = re.search(r"\b(?:[A-Za-z]\s+){3,}[A-Za-z]\b", raw.replace("&nbsp;", " "))
        if spaced:
            directives.append({"kind": "spaced", "text": spaced.group(0)})
        tiny = re.findall(r"\*([a-z]{3,10})\*", raw)
        for token in tiny:
            directives.append({"kind": "tiny", "text": token})
    return directives

def parse_trim_size(size: str) -> Tuple[float, float]:
    w, h = size.lower().split("x")
    return float(w), float(h)


def fit_cover_image_to_rect(approved_cover: Path, target_w_px: int, target_h_px: int) -> Path:
    with Image.open(approved_cover) as im:
        rgb = im.convert("RGB")
        src_ratio = rgb.width / max(1, rgb.height)
        target_ratio = target_w_px / max(1, target_h_px)
        if src_ratio > target_ratio:
            new_w = int(rgb.height * target_ratio)
            left = max(0, (rgb.width - new_w) // 2)
            crop = rgb.crop((left, 0, left + new_w, rgb.height))
        else:
            new_h = int(rgb.width / max(target_ratio, 1e-6))
            top = max(0, (rgb.height - new_h) // 2)
            crop = rgb.crop((0, top, rgb.width, top + new_h))
        fitted = crop.resize((target_w_px, target_h_px), Image.Resampling.LANCZOS)
    fd, name = tempfile.mkstemp(prefix="bookforge_fit_", suffix=".jpg")
    Path(name).unlink(missing_ok=True)
    out = Path(name)
    fitted.save(out, format="JPEG", quality=95)
    return out


class PDFLayoutEngine:
    def __init__(self, font_path: Path) -> None:
        self.font_name = "NotoSans"
        self.font_path = font_path
        self.font_fallback_reason = ""
        try:
            pdfmetrics.registerFont(TTFont(self.font_name, str(self.font_path)))
        except Exception:
            self.font_name = "Helvetica"
            self.font_fallback_reason = (
                "Font embed failed for assets/fonts/NotoSans-Regular.ttf; "
                "falling back to Helvetica."
            )

    def _soften_widow(self, text: str) -> str:
        parts = text.split()
        if len(parts) > 3:
            parts[-2] = parts[-2] + "&nbsp;" + parts[-1]
            parts.pop()
        return " ".join(parts)

    def _hyphenate_text(self, text: str) -> str:
        if pyphen is None:
            return text
        dic = pyphen.Pyphen(lang="en_US")
        out = []
        for word in text.split():
            if len(word) > 10:
                out.append(dic.inserted(word, hyphen="&#8209;"))
            else:
                out.append(word)
        return " ".join(out)

    def _sample_region_luminance(self, image_path: Path, region: Tuple[int, int, int, int]) -> float:
        with Image.open(image_path) as im:
            rgb = im.convert("RGB")
            x0, y0, x1, y1 = region
            crop = rgb.crop((max(0, x0), max(0, y0), min(rgb.width, x1), min(rgb.height, y1)))
            if crop.width == 0 or crop.height == 0:
                return 255.0
            px = list(crop.getdata())
        return sum((0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in px) / max(len(px), 1)

    def _region_busyness(self, image_path: Path, region: Tuple[int, int, int, int]) -> float:
        with Image.open(image_path) as im:
            arr = im.convert("L")
            x0, y0, x1, y1 = region
            crop = np.asarray(arr.crop((max(0, x0), max(0, y0), min(arr.width, x1), min(arr.height, y1))), dtype=np.float32)
            if crop.size == 0:
                return 0.0
            gx = np.zeros_like(crop)
            gy = np.zeros_like(crop)
            gx[:, 1:-1] = crop[:, 2:] - crop[:, :-2]
            gy[1:-1, :] = crop[2:, :] - crop[:-2, :]
            return float(np.mean(np.sqrt(gx * gx + gy * gy)))

    def _choose_text_colors(self, image_path: Path, region: Tuple[int, int, int, int], threshold: float = 140.0) -> Tuple[Any, Any]:
        lum = self._sample_region_luminance(image_path, region)
        return (black, white) if lum >= threshold else (white, black)

    def _draw_stroked_centred_text(self, c: canvas.Canvas, x: float, y: float, text: str, main_color: Any, stroke_color: Any, stroke_offset: float = 1.0) -> None:
        c.setFillColor(stroke_color)
        for dx, dy in ((-stroke_offset, 0), (stroke_offset, 0), (0, -stroke_offset), (0, stroke_offset)):
            c.drawCentredString(x + dx, y + dy, text)
        c.setFillColor(main_color)
        c.drawCentredString(x, y, text)

    def _draw_typography_overlays(self, c: canvas.Canvas, directives: List[Dict[str, Any]], page_w: float, page_h: float, safe_x: float, safe_y: float, safe_w: float, safe_h: float) -> None:
        for i, d in enumerate(directives):
            kind = str(d.get("type", "")).strip()
            if kind == "display_word":
                txt = str(d.get("text", "")).strip()
                if not txt:
                    continue
                c.setFont(self.font_name, 58)
                self._draw_stroked_centred_text(c, page_w / 2, safe_y + safe_h * 0.24, txt, black, white, stroke_offset=1.4)
            elif kind == "micro_word":
                txt = str(d.get("text", "")).strip()
                if not txt:
                    continue
                c.setFont(self.font_name, 8)
                drift = i * 6
                self._draw_stroked_centred_text(c, page_w * 0.52, safe_y + 20 - drift, txt, black, white, stroke_offset=0.6)
            elif kind == "spaced_words":
                frag = str(d.get("raw_fragment", "")).replace("&nbsp;", " ").strip()
                tokens = [t for t in frag.split() if t]
                if not tokens:
                    continue
                c.setFont(self.font_name, 14)
                y = safe_y + safe_h * 0.12
                step = safe_w / (len(tokens) + 1)
                for t_idx, tok in enumerate(tokens, start=1):
                    self._draw_stroked_centred_text(c, safe_x + step * t_idx, y, tok, black, white, stroke_offset=0.8)

    def _normalized_to_page_rect(self, rect: Dict[str, float], page_w: float, page_h: float) -> Tuple[float, float, float, float]:
        x = max(0.0, min(page_w, float(rect.get("x", 0.0)) * page_w))
        y = max(0.0, min(page_h, float(rect.get("y", 0.0)) * page_h))
        w = max(1.0, min(page_w - x, float(rect.get("w", 1.0)) * page_w))
        h = max(1.0, min(page_h - y, float(rect.get("h", 1.0)) * page_h))
        return x, y, w, h

    def _draw_image_zone(self, c: canvas.Canvas, image_path: Path, zone: Dict[str, float], page_w: float, page_h: float, preserve_aspect: bool = True, stroke: bool = False) -> None:
        x, y, w, h = self._normalized_to_page_rect(zone, page_w, page_h)
        c.drawImage(ImageReader(str(image_path)), x, y, w, h, preserveAspectRatio=preserve_aspect, anchor="c")
        if stroke:
            c.setStrokeColorRGB(1, 1, 1)
            c.setLineWidth(1.2)
            c.roundRect(x, y, w, h, 6, stroke=1, fill=0)

    def _safe_rect(self, safe_x: float, safe_y: float, safe_w: float, safe_h: float) -> Dict[str, float]:
        return {"x": safe_x, "y": safe_y, "w": safe_w, "h": safe_h}

    def _zone_to_safe_bounds(self, zone: Dict[str, float], safe_x: float, safe_y: float, safe_w: float, safe_h: float, page_w: float, page_h: float) -> Tuple[float, float, float, float]:
        x, y, w, h = self._normalized_to_page_rect(zone, page_w, page_h)
        x0 = max(safe_x, x)
        y0 = max(safe_y, y)
        x1 = min(safe_x + safe_w, x + w)
        y1 = min(safe_y + safe_h, y + h)
        return x0, y0, max(1.0, x1 - x0), max(1.0, y1 - y0)

    def render_interior(self, pages: List[Dict[str, Any]], image_paths: List[str], output_interior: Path, size: str, bleed_in: float, safe_margin_in: float, layout_preset: Dict[str, Any], typography_preset: Dict[str, Any], pdf_options: Dict[str, Any] | None = None, spread_pairs: List[Tuple[int, int]] | None = None, architecture_layout: Dict[int, Dict[str, Any]] | None = None) -> Dict[str, Any]:
        trim_w, trim_h = parse_trim_size(size)
        page_w = (trim_w + bleed_in * 2) * 72
        page_h = (trim_h + bleed_in * 2) * 72
        c = canvas.Canvas(str(output_interior), pagesize=(page_w, page_h), pageCompression=1)
        safe_x = (bleed_in + safe_margin_in) * 72
        safe_y = (bleed_in + safe_margin_in) * 72
        safe_w = (trim_w - 2 * safe_margin_in) * 72
        safe_h = (trim_h - 2 * safe_margin_in) * 72

        options = pdf_options or {}
        embed_mode = str(options.get("image_embed", "jpeg")).lower()
        jpeg_quality = int(options.get("jpeg_quality", 92))
        spread_page_set = {p for pair in (spread_pairs or []) for p in pair}
        applied_layout: List[Dict[str, Any]] = []
        for page, img_path in zip(pages, image_paths):
            page_no = int(page.get("page_number", 0))
            arch = (architecture_layout or {}).get(page_no, {})
            embed_path = Path(img_path)
            temp_path: Path | None = None
            if embed_mode == "jpeg":
                with Image.open(embed_path) as im:
                    rgb = im.convert("RGB")
                    temp_path = output_interior.parent / f".tmp_embed_{page['page_number']:03d}.jpg"
                    rgb.save(temp_path, format="JPEG", quality=jpeg_quality, subsampling=0)
                embed_path = temp_path
            mode = str((arch.get("compositor_hints", {}) or {}).get("mode", "legacy_default"))
            if mode in {"full_bleed_spread", "wordless_spread", "full_bleed_single_art_page", "legacy_default"}:
                c.drawImage(ImageReader(str(embed_path)), 0, 0, page_w, page_h, preserveAspectRatio=False, anchor="c")
            elif mode in {"vignette", "spot_illustration", "text_dominant", "full_bleed_single_text_page"}:
                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
                self._draw_image_zone(c, embed_path, arch.get("art_zone", {"x": 0.08, "y": 0.4, "w": 0.84, "h": 0.5}), page_w, page_h, preserve_aspect=True)
            elif mode == "panel_sequence":
                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
                for panel in arch.get("panel_zones", [])[:3]:
                    self._draw_image_zone(c, embed_path, panel, page_w, page_h, preserve_aspect=True)
            elif mode == "inset_composite":
                self._draw_image_zone(c, embed_path, arch.get("art_zone", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}), page_w, page_h, preserve_aspect=False)
                for inset in arch.get("inset_zones", []):
                    self._draw_image_zone(c, embed_path, inset, page_w, page_h, preserve_aspect=True, stroke=True)
            else:
                c.drawImage(ImageReader(str(embed_path)), 0, 0, page_w, page_h, preserveAspectRatio=False, anchor="c")
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            panel_h = safe_h * layout_preset["panel_height_ratio"]
            panel_y = safe_y if layout_preset["panel_position"] == "bottom" else safe_y + safe_h - panel_h
            panel_x = safe_x
            panel_w = safe_w
            layout_fallback = ""
            if isinstance(arch, dict) and arch.get("text_zone"):
                zx, zy, zw, zh = self._zone_to_safe_bounds(arch["text_zone"], safe_x, safe_y, safe_w, safe_h, page_w, page_h)
                panel_x, panel_y, panel_w, panel_h = zx, zy, zw, zh
                if str(arch.get("page_side", "")) == "verso" and bool(arch.get("gutter_sensitive", False)):
                    gutter_clearance = page_w * 0.06
                    if panel_x < gutter_clearance:
                        shift = gutter_clearance - panel_x
                        panel_x = min(page_w - panel_w, panel_x + shift)
                    if panel_x + panel_w > page_w - gutter_clearance:
                        panel_w = max(1.0, (page_w - gutter_clearance) - panel_x)
                if panel_w < 40 or panel_h < 30:
                    panel_h = safe_h * layout_preset["panel_height_ratio"]
                    panel_y = safe_y if layout_preset["panel_position"] == "bottom" else safe_y + safe_h - panel_h
                    panel_x = safe_x
                    panel_w = safe_w
                    layout_fallback = "pas_text_zone_too_small_for_typography"
            c.setFillColorRGB(1, 1, 1)
            if not bool(arch.get("suppress_body_text", False)):
                c.roundRect(panel_x, panel_y, panel_w, panel_h, 8, stroke=0, fill=1)

            raw_text = self._soften_widow(self._hyphenate_text(page["text"].strip()))
            font_size = typography_preset["base_font_size"]
            para_h = panel_h - 2 * layout_preset["panel_padding_pt"]
            para_w = panel_w - 2 * layout_preset["panel_padding_pt"]
            para = None
            if not bool(arch.get("suppress_body_text", False)):
                while font_size >= typography_preset["min_font_size"]:
                    style = ParagraphStyle(
                        name="body",
                        fontName=self.font_name,
                        fontSize=font_size,
                        leading=font_size * typography_preset["leading"],
                        alignment=1 if layout_preset["text_align"] == "center" else 0,
                        textColor=black,
                    )
                    para = Paragraph(raw_text, style)
                    _, needed_h = para.wrap(para_w, para_h)
                    if needed_h <= para_h:
                        break
                    font_size -= 1
                if para is None or font_size < typography_preset["min_font_size"]:
                    if arch:
                        panel_h = safe_h * layout_preset["panel_height_ratio"]
                        panel_y = safe_y if layout_preset["panel_position"] == "bottom" else safe_y + safe_h - panel_h
                        panel_x = safe_x
                        panel_w = safe_w
                        para_h = panel_h - 2 * layout_preset["panel_padding_pt"]
                        para_w = panel_w - 2 * layout_preset["panel_padding_pt"]
                        font_size = typography_preset["base_font_size"]
                        while font_size >= typography_preset["min_font_size"]:
                            style = ParagraphStyle(
                                name="body_fallback",
                                fontName=self.font_name,
                                fontSize=font_size,
                                leading=font_size * typography_preset["leading"],
                                alignment=1 if layout_preset["text_align"] == "center" else 0,
                                textColor=black,
                            )
                            para = Paragraph(raw_text, style)
                            _, needed_h = para.wrap(para_w, para_h)
                            if needed_h <= para_h:
                                layout_fallback = layout_fallback or "pas_text_zone_overflow_fallback_to_preset"
                                break
                            font_size -= 1
                    if para is None or font_size < typography_preset["min_font_size"]:
                        raise RuntimeError(f"Text overflow could not be resolved on page {page['page_number']}. Reduce text or choose a larger panel preset.")

                para.drawOn(c, panel_x + layout_preset["panel_padding_pt"], panel_y + panel_h - layout_preset["panel_padding_pt"] - needed_h)
            directives = page.get("typography_directives", []) if isinstance(page, dict) else []
            typography_plan_payload = page.get("typography_plan") if isinstance(page, dict) else None
            typography_render_meta: Dict[str, Any] = {"overlay_count": 0, "fallback_used": False, "style_roles": []}
            if isinstance(typography_plan_payload, dict):
                try:
                    plan = PageTypographyPlan(
                        page_number=int(typography_plan_payload.get("page_number", page_no)),
                        source_markdown=str(typography_plan_payload.get("source_markdown", "")),
                        text_zone=typography_plan_payload.get("text_zone", {"x": 0.08, "y": 0.06, "w": 0.84, "h": 0.22}),
                        alignment=str(typography_plan_payload.get("alignment", "left")),
                        preferred_region=str(typography_plan_payload.get("preferred_region", "lower_safe")),
                        body_scale_class=str(typography_plan_payload.get("body_scale_class", "body")),
                        style_roles=[str(x) for x in typography_plan_payload.get("style_roles", [])],
                        lines=[],
                        directives=[],
                        quietness_requirement=float(typography_plan_payload.get("quietness_requirement", 0.5) or 0.5),
                        contrast_requirement=float(typography_plan_payload.get("contrast_requirement", 0.65) or 0.65),
                        overflow_expected=bool(typography_plan_payload.get("overflow_expected", False)),
                        special_positioning_mode=str(typography_plan_payload.get("special_positioning_mode", "anchored")),
                        warnings=[str(x) for x in typography_plan_payload.get("warnings", [])],
                        notes=[str(x) for x in typography_plan_payload.get("notes", [])],
                    )
                    line_rows = typography_plan_payload.get("lines", []) if isinstance(typography_plan_payload.get("lines", []), list) else []
                    directive_rows = typography_plan_payload.get("directives", []) if isinstance(typography_plan_payload.get("directives", []), list) else []
                    from bookforge.typography.types import TypographyDirective, TypographyLinePlan, TypographySpan

                    lines = []
                    for row in line_rows:
                        if not isinstance(row, dict):
                            continue
                        spans = []
                        for sp in row.get("spans", []) if isinstance(row.get("spans", []), list) else []:
                            if not isinstance(sp, dict):
                                continue
                            spans.append(TypographySpan(
                                text=str(sp.get("text", "")),
                                role=str(sp.get("role", "body")),
                                emphasis=float(sp.get("emphasis", 0.4) or 0.4),
                                scale_class=str(sp.get("scale_class", "body")),
                                weight_class=str(sp.get("weight_class", "regular")),
                                directional_drift=str(sp.get("directional_drift", "none")),
                                preserve_exact_text=bool(sp.get("preserve_exact_text", True)),
                            ))
                        lines.append(TypographyLinePlan(
                            line_text=str(row.get("line_text", "")),
                            role=str(row.get("role", "body")),
                            alignment=str(row.get("alignment", "left")),
                            scale_class=str(row.get("scale_class", "body")),
                            weight_class=str(row.get("weight_class", "regular")),
                            line_gap_multiplier=float(row.get("line_gap_multiplier", 1.0) or 1.0),
                            spans=spans,
                        ))
                    plan = PageTypographyPlan(
                        page_number=plan.page_number,
                        source_markdown=plan.source_markdown,
                        text_zone=plan.text_zone,
                        alignment=plan.alignment,
                        preferred_region=plan.preferred_region,
                        body_scale_class=plan.body_scale_class,
                        style_roles=plan.style_roles,
                        lines=lines,
                        directives=[TypographyDirective(
                            kind=str(d.get("kind", "")),
                            text=str(d.get("text", "")),
                            role=str(d.get("role", "body")),
                            line_index=int(d.get("line_index", 0) or 0),
                            strength=float(d.get("strength", 0.5) or 0.5),
                            metadata=d.get("metadata", {}) if isinstance(d.get("metadata", {}), dict) else {},
                        ) for d in directive_rows if isinstance(d, dict)],
                        quietness_requirement=plan.quietness_requirement,
                        contrast_requirement=plan.contrast_requirement,
                        overflow_expected=plan.overflow_expected,
                        special_positioning_mode=plan.special_positioning_mode,
                        warnings=plan.warnings,
                        notes=plan.notes,
                    )
                    typography_render_meta = draw_typography_plan(
                        c,
                        plan=plan,
                        font_name=self.font_name,
                        page_w=page_w,
                        safe_x=safe_x,
                        safe_y=safe_y,
                        safe_w=safe_w,
                        safe_h=safe_h,
                        base_font_size=font_size,
                    )
                except Exception:
                    typography_render_meta["fallback_used"] = True
            if typography_render_meta.get("fallback_used", False) and isinstance(directives, list) and directives:
                self._draw_typography_overlays(c, directives, page_w, page_h, safe_x, safe_y, safe_w, safe_h)
            if layout_preset["show_page_numbers"]:
                c.setFillColor(black)
                c.setFont(self.font_name, 9)
                c.drawRightString(page_w - safe_x, safe_y - 14, str(page["page_number"]))
            applied_layout.append(
                {
                    "page": page_no,
                    "architecture_type": arch.get("architecture_type", "none") if isinstance(arch, dict) else "none",
                    "variant_id": arch.get("variant_id", "") if isinstance(arch, dict) else "",
                    "layout_mode": mode,
                    "suppress_body_text": bool(arch.get("suppress_body_text", False)) if isinstance(arch, dict) else False,
                    "gutter_safe_applied": bool(arch.get("gutter_safe_applied", False)) if isinstance(arch, dict) else False,
                    "layout_fallback_reason": layout_fallback or (arch.get("layout_fallback_reason", "") if isinstance(arch, dict) else ""),
                    "typography_overlay_count": int(typography_render_meta.get("overlay_count", 0) or 0),
                    "typography_render_fallback": bool(typography_render_meta.get("fallback_used", False)),
                    "typography_style_roles": typography_render_meta.get("style_roles", []),
                    "layout_search_chosen_permutation_id": str(((arch.get("layout_search", {}) or {}).get("chosen_permutation_id", "")) if isinstance(arch, dict) else ""),
                    "layout_search_top_score": float(((arch.get("layout_search", {}) or {}).get("top_score", 0.0)) if isinstance(arch, dict) else 0.0),
                    "layout_search_scope": str(arch.get("layout_search_scope", "")) if isinstance(arch, dict) else "",
                    "layout_search_changed_fields": list((((arch.get("layout_search", {}) or {}).get("applied_changes", {}) or {}).get("changed_fields", [])) if isinstance(arch, dict) else []),
                    "layout_search_text_zone_delta": dict((((arch.get("layout_search", {}) or {}).get("applied_changes", {}) or {}).get("text_zone_delta", {})) if isinstance(arch, dict) else {}),
                    "layout_search_art_zone_delta": dict((((arch.get("layout_search", {}) or {}).get("applied_changes", {}) or {}).get("art_zone_delta", {})) if isinstance(arch, dict) else {}),
                }
            )
            c.showPage()
        c.save()
        return {"page_dimensions_pt": [page_w, page_h], "spread_page_set": sorted(spread_page_set), "applied_page_architecture": applied_layout}

    def render_cover_wrap(self, output_cover: Path, output_guides: Path, trim_w: float, trim_h: float, bleed_in: float, safe_margin_in: float, page_count: int, spine_w: float, title: str, author: str, approved_cover: Path, approved_style: Path, cover_preset: Dict[str, Any], cover_config: Dict[str, Any]) -> Dict[str, Any]:
        cover_w = 2 * trim_w + spine_w + 2 * bleed_in
        cover_h = trim_h + 2 * bleed_in
        w_pt, h_pt = cover_w * 72, cover_h * 72
        c = canvas.Canvas(str(output_cover), pagesize=(w_pt, h_pt), pageCompression=1)

        back_x = bleed_in * 72
        spine_x = (bleed_in + trim_w) * 72
        front_x = (bleed_in + trim_w + spine_w) * 72
        panel_y = bleed_in * 72
        panel_h = trim_h * 72

        if cover_preset["back_background_mode"] == "style_blur" and approved_style.exists():
            with Image.open(approved_style) as im:
                blur = im.convert("RGB").filter(ImageFilter.GaussianBlur(radius=6))
                tmp_blur = output_cover.parent / ".tmp_style_blur.jpg"
                blur.save(tmp_blur, format="JPEG", quality=90)
            fitted_blur = fit_cover_image_to_rect(tmp_blur, int(round(w_pt)), int(round(h_pt)))
            c.drawImage(ImageReader(str(fitted_blur)), 0, 0, w_pt, h_pt, preserveAspectRatio=False, anchor="c")
            fitted_blur.unlink(missing_ok=True)
            tmp_blur.unlink(missing_ok=True)
        else:
            c.setFillColorRGB(0.94, 0.93, 0.9)
            c.rect(0, 0, w_pt, h_pt, stroke=0, fill=1)

        front_w = (trim_w + bleed_in) * 72
        front_h = h_pt
        fitted_cover = fit_cover_image_to_rect(approved_cover, int(round(front_w)), int(round(front_h)))
        c.drawImage(ImageReader(str(fitted_cover)), front_x, 0, front_w, front_h, preserveAspectRatio=False, anchor="c")
        fitted_cover.unlink(missing_ok=True)
        c.setFont(self.font_name, 30)
        candidate_y = {
            "top": panel_y + panel_h - 50,
            "middle": panel_y + panel_h / 2,
            "bottom": panel_y + 42,
        }
        placement = cover_preset["title_placement"]
        if placement == "auto":
            candidates = {
                name: (int(front_x), int(max(0, y - 40)), int(front_x + trim_w * 72), int(min(h_pt, y + 40)))
                for name, y in candidate_y.items()
            }
            least_busy = min(candidates.items(), key=lambda kv: self._region_busyness(approved_cover, kv[1]))[0]
            title_y = candidate_y[least_busy]
        elif placement == "front_top":
            title_y = candidate_y["top"]
        elif placement == "front_bottom":
            title_y = candidate_y["bottom"]
        else:
            title_y = candidate_y["middle"]
        title_region = (int(front_x), int(max(0, title_y - 40)), int(front_x + trim_w * 72), int(min(h_pt, title_y + 40)))
        title_color, title_outline = self._choose_text_colors(approved_cover, title_region)
        self._draw_stroked_centred_text(c, front_x + trim_w * 36, title_y, title, title_color, title_outline, stroke_offset=1.2)

        c.setFont(self.font_name, 14)
        author_y = panel_y + 20 if cover_preset["author_placement"] == "front_bottom" else panel_y + panel_h - 78
        author_region = (int(front_x), int(max(0, author_y - 24)), int(front_x + trim_w * 72), int(min(h_pt, author_y + 24)))
        author_color, author_outline = self._choose_text_colors(approved_cover, author_region)
        self._draw_stroked_centred_text(c, front_x + trim_w * 36, author_y, author, author_color, author_outline, stroke_offset=1.0)
        if spine_w >= cover_config["spine_text_min_in"]:
            c.saveState()
            c.translate(spine_x + (spine_w * 72) / 2, panel_y + panel_h / 2)
            c.rotate(90)
            c.setFont(self.font_name, 12)
            c.drawCentredString(0, 0, title)
            c.restoreState()

        subtitle = str(cover_config.get("subtitle", "")).strip()
        if subtitle:
            c.setFont(self.font_name, 12)
            subtitle_y = max(panel_y + 24, title_y - 24) if cover_preset["title_placement"] == "auto" else author_y - 22
            self._draw_stroked_centred_text(c, front_x + trim_w * 36, subtitle_y, subtitle, author_color, author_outline, stroke_offset=0.8)

        blurb = str(cover_config.get("back_blurb", "")).strip()
        if blurb:
            bbx, bby, bbw, bbh = cover_preset.get("blurb_box_in", [0.6, 2.0, max(1.0, trim_w - 1.2), max(1.0, trim_h - 3.0)])
            x = back_x + bbx * 72
            y = panel_y + bby * 72
            w = bbw * 72
            h = bbh * 72
            bx, by, bw, bh = cover_preset["barcode_box_in"]
            bb = (x, y, x + w, y + h)
            barcode = (back_x + bx * 72, panel_y + by * 72, back_x + (bx + bw) * 72, panel_y + (by + bh) * 72)
            overlap = not (bb[2] <= barcode[0] or bb[0] >= barcode[2] or bb[3] <= barcode[1] or bb[1] >= barcode[3])
            if overlap:
                raise RuntimeError("Blurb box overlaps barcode box. Update cover preset geometry.")
            style = ParagraphStyle(name="blurb", fontName=self.font_name, fontSize=10, leading=12, textColor=black, alignment=0)
            para = Paragraph(blurb, style)
            _, needed_h = para.wrap(w, h)
            if needed_h > h:
                raise RuntimeError("Back-cover blurb overflowed blurb box. Choose a shorter blurb or larger blurb box preset.")
            para.drawOn(c, x, y + h - needed_h)

        bx, by, bw, bh = cover_preset["barcode_box_in"]
        c.setFillColor(white)
        c.rect(back_x + bx * 72, panel_y + by * 72, bw * 72, bh * 72, stroke=0, fill=1)
        c.save()

        g = canvas.Canvas(str(output_guides), pagesize=(w_pt, h_pt), pageCompression=1)
        g.rect(back_x, panel_y, (2 * trim_w + spine_w) * 72, panel_h)
        g.rect((bleed_in + safe_margin_in) * 72, (bleed_in + safe_margin_in) * 72, (2 * trim_w + spine_w - 2 * safe_margin_in) * 72, (trim_h - 2 * safe_margin_in) * 72)
        g.line(spine_x, panel_y, spine_x, panel_y + panel_h)
        g.line(front_x, panel_y, front_x, panel_y + panel_h)
        g.save()
        return {"cover_w_in": cover_w, "cover_h_in": cover_h, "back_background_rect_pt": [0, 0, w_pt, h_pt], "front_art_rect_pt": [front_x, 0, (trim_w + bleed_in) * 72, h_pt], "spine_rect_pt": [spine_x, panel_y, spine_w * 72, panel_h]}

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
