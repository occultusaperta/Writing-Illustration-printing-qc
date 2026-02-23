from __future__ import annotations

from typing import Any, Dict, List


def generate_trade_dress(lock: Dict[str, Any], cover_preset: Dict[str, Any], palette: List[str]) -> Dict[str, Any]:
    return {
        "cover_grid_template_notes": f"Use preset {cover_preset.get('id', 'default')} with stable title area and badge anchor.",
        "title_typography_rule": f"Primary title uses {lock.get('typography_preset', 'storybook_large')} with consistent case across series.",
        "recurring_badge_icon_location": "Top-right badge zone, clear of focal character silhouette.",
        "series_motif_token_list": palette[:4] + ["series-star", "spine-band"],
    }
