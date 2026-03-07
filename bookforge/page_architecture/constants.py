from __future__ import annotations

TRIM_WIDTH_IN = 8.5
TRIM_HEIGHT_IN = 8.5
BLEED_IN = 0.125
SAFE_MARGIN_IN = 0.375
GUTTER_MARGIN_IN = 0.25
DPI = 300

TRIM_WIDTH_PX = int(TRIM_WIDTH_IN * DPI)
TRIM_HEIGHT_PX = int(TRIM_HEIGHT_IN * DPI)
FULL_WIDTH_PX = int((TRIM_WIDTH_IN + 2 * BLEED_IN) * DPI)
FULL_HEIGHT_PX = int((TRIM_HEIGHT_IN + 2 * BLEED_IN) * DPI)
SAFE_LEFT_N = (BLEED_IN + SAFE_MARGIN_IN) / (TRIM_WIDTH_IN + 2 * BLEED_IN)
SAFE_TOP_N = (BLEED_IN + SAFE_MARGIN_IN) / (TRIM_HEIGHT_IN + 2 * BLEED_IN)
SAFE_RIGHT_N = 1.0 - SAFE_LEFT_N
SAFE_BOTTOM_N = 1.0 - SAFE_TOP_N

SUITABILITY_MATRIX = {
    "opening": {"text_dominant": 0.75, "full_bleed_single": 0.70, "vignette": 0.62},
    "rising_action": {"panel_sequence": 0.82, "full_bleed_single": 0.70, "inset_composite": 0.66},
    "climax": {"full_bleed_spread": 0.92, "wordless_spread": 0.88, "panel_sequence": 0.55},
    "falling_action": {"vignette": 0.78, "spot_illustration": 0.73, "text_dominant": 0.64},
    "resolution": {"text_dominant": 0.82, "spot_illustration": 0.74, "vignette": 0.70},
}
