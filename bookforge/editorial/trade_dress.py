from __future__ import annotations

from typing import Any, Dict, List


def generate_trade_dress(lock: Dict[str, Any], cover_preset: Dict[str, Any], palette: List[str]) -> Dict[str, Any]:
    typography = lock.get("typography_preset", "storybook_large")
    return {
        "cover_grid_template_notes": f"Use preset {cover_preset.get('id', 'default')} with stable title area and badge anchor.",
        "title_typography_rule": f"Primary title uses {typography} with consistent case across series.",
        "readaloud_clarity_typography_presets": ["storybook_large", "imprint_caption_lux", "participatory_xheight_sans"],
        "large_xheight_sans_option": "participatory_xheight_sans",
        "dramatic_vector_text_directives": ["display_word", "spaced_words", "micro_word"],
        "cover_hierarchy_scoring_targets": {"title_weight": 0.40, "character_weight": 0.30, "subtitle_weight": 0.20, "author_weight": 0.10},
        "series_trade_dress_metadata": {
            "series_band": "top-right badge zone",
            "palette_lock": palette[:5],
            "motif_tokens": palette[:4] + ["series-star", "spine-band"],
        },
        "spine_rules": {
            "color_block": palette[0] if palette else "#1F2A44",
            "numbering": "series_number_optional",
            "identifier": "spine_short_code_required",
        },
        "barcode_safe_checks": {"enabled": True, "box_in": cover_preset.get("barcode_box_in", [0.6, 0.6, 2.0, 1.2])},
        "title_safe_checks": {"enabled": True, "avoid_busy_regions": True},
        "cover_readability_busyness_scoring": {"max_busyness": 0.62, "min_readability": 0.70},
        "recurring_badge_icon_location": "Top-right badge zone, clear of focal character silhouette.",
    }
