from __future__ import annotations

from typing import Dict, Tuple


Rect = Tuple[float, float, float, float]
Point = Tuple[float, float]


def _point_in_rect(point: Point, rect: Rect) -> bool:
    x, y = point
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def verify_text_panel_not_competing(focus_centroid: Point, panel_rect: Rect) -> Dict[str, str]:
    if _point_in_rect(focus_centroid, panel_rect):
        return {
            "status": "warn",
            "message": "Primary focus competes with caption strip.",
            "suggestion": "move focal action upward; keep key faces away from bottom edge",
        }
    return {"status": "pass", "message": "Text panel placement clear.", "suggestion": "none"}


def verify_focus_not_covered_by_panel(focus_centroid: Point, panel_rect: Rect) -> Dict[str, str]:
    return verify_text_panel_not_competing(focus_centroid, panel_rect)
