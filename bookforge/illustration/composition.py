from __future__ import annotations

from typing import Dict, Tuple


def compute_rule_of_thirds_grid(width: int, height: int) -> Dict[str, Tuple[int, int]]:
    """Return canonical rule-of-thirds focal points for a frame."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    x1 = round(width / 3)
    x2 = round((width * 2) / 3)
    y1 = round(height / 3)
    y2 = round((height * 2) / 3)
    return {
        "thirds_top_left": (x1, y1),
        "thirds_top_right": (x2, y1),
        "thirds_bottom_left": (x1, y2),
        "thirds_bottom_right": (x2, y2),
    }


def compute_golden_ratio_points(width: int, height: int) -> Dict[str, Tuple[int, int]]:
    """Return golden-ratio-inspired focal anchors for composition guidance."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    phi = 0.61803398875
    x_left = round(width * (1 - phi))
    x_right = round(width * phi)
    y_top = round(height * (1 - phi))
    y_bottom = round(height * phi)
    return {
        "golden_ratio_top_left": (x_left, y_top),
        "golden_ratio_top_right": (x_right, y_top),
        "golden_ratio_bottom_left": (x_left, y_bottom),
        "golden_ratio_bottom_right": (x_right, y_bottom),
    }
