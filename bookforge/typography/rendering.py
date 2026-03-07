from __future__ import annotations

from typing import Any, Dict, Tuple

from reportlab.lib.colors import black, white
from reportlab.pdfgen import canvas

from bookforge.typography.types import PageTypographyPlan


def _font_size_from_class(base_font_size: float, scale_class: str) -> float:
    mapping = {
        "xs": 0.68,
        "sm": 0.82,
        "body": 1.0,
        "lg": 1.16,
        "xl": 1.34,
        "xxl": 1.58,
    }
    return float(base_font_size * mapping.get(scale_class, 1.0))


def draw_typography_plan(
    c: canvas.Canvas,
    *,
    plan: PageTypographyPlan,
    font_name: str,
    page_w: float,
    safe_x: float,
    safe_y: float,
    safe_w: float,
    safe_h: float,
    base_font_size: float,
) -> Dict[str, Any]:
    overlay_count = 0
    fallback_used = False
    for idx, line in enumerate(plan.lines):
        if line.role == "body":
            continue
        if not line.line_text.strip():
            continue
        size = _font_size_from_class(base_font_size, line.scale_class)
        size = max(6.0, min(76.0, size))
        c.setFont(font_name, size)

        x = safe_x + safe_w * 0.5
        if line.alignment == "left":
            x = safe_x + safe_w * 0.12
        elif line.alignment == "right":
            x = safe_x + safe_w * 0.88

        y = safe_y + safe_h * (0.26 + 0.08 * min(idx, 5))
        if line.role == "whisper":
            y = max(safe_y + 8, safe_y + 14 - 5 * idx)
        if line.role == "directional":
            x = min(page_w - safe_x, x + safe_w * 0.08)

        stroke_offset = 0.9 if line.role != "whisper" else 0.5
        c.setFillColor(white)
        for dx, dy in ((-stroke_offset, 0), (stroke_offset, 0), (0, -stroke_offset), (0, stroke_offset)):
            c.drawCentredString(x + dx, y + dy, line.line_text.strip())
        c.setFillColor(black)
        c.drawCentredString(x, y, line.line_text.strip())
        if line.weight_class in {"bold", "semibold"}:
            c.drawCentredString(x + 0.35, y, line.line_text.strip())
        overlay_count += 1

    if overlay_count == 0:
        fallback_used = True

    return {
        "overlay_count": overlay_count,
        "fallback_used": fallback_used,
        "style_roles": plan.style_roles,
        "special_positioning_mode": plan.special_positioning_mode,
    }
