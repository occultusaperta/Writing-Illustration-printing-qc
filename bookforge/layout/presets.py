from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class InteriorLayoutPreset:
    id: str
    name: str
    description: str
    panel_position: str
    panel_height_ratio: float
    panel_padding_pt: int
    text_align: str
    show_page_numbers: bool


@dataclass(frozen=True)
class TypographyPreset:
    id: str
    name: str
    base_font_size: int
    min_font_size: int
    leading: float
    max_lines: int
    tracking_mode: str


@dataclass(frozen=True)
class CoverLayoutPreset:
    id: str
    name: str
    description: str
    title_placement: str
    author_placement: str
    spine_text_rule: str
    back_blurb_box: str
    blurb_box_in: list[float]
    barcode_box_in: list[float]
    back_background_mode: str


INTERIOR_LAYOUT_PRESETS: List[InteriorLayoutPreset] = [
    InteriorLayoutPreset("cinematic_panel_bottom", "Cinematic Bottom", "Wide text panel anchored at bottom for image-first spreads.", "bottom", 0.32, 18, "left", True),
    InteriorLayoutPreset("gallery_panel_top", "Gallery Top", "Top text panel with centered copy for calm story pacing.", "top", 0.30, 16, "center", False),
    InteriorLayoutPreset("storybook_balanced_bottom", "Storybook Balanced", "Balanced lower panel for medium narration density.", "bottom", 0.36, 20, "left", True),
    InteriorLayoutPreset("luxe_caption_top", "Luxe Caption", "Slim top caption treatment with generous margins.", "top", 0.26, 22, "center", False),
    InteriorLayoutPreset("imprint_image_heavy_bottom_strip", "Imprint Image-Heavy Bottom Strip", "Premium caption strip that preserves art for image-heavy layouts.", "bottom", 0.20, 18, "center", False),
]

TYPOGRAPHY_PRESETS: List[TypographyPreset] = [
    TypographyPreset("storybook_large", "Storybook Large", 20, 14, 1.25, 8, "normal"),
    TypographyPreset("storybook_balanced", "Storybook Balanced", 18, 12, 1.3, 10, "normal"),
    TypographyPreset("storybook_compact", "Storybook Compact", 16, 11, 1.28, 12, "tight"),
    TypographyPreset("imprint_caption_lux", "Imprint Caption Lux", 22, 14, 1.15, 5, "normal"),
    TypographyPreset("participatory_xheight_sans", "Participatory X-Height Sans", 24, 15, 1.18, 5, "normal"),
]

COVER_LAYOUT_PRESETS: List[CoverLayoutPreset] = [
    CoverLayoutPreset("front_title_top_back_blurb", "Title Top / Back Blurb", "Classic premium layout with title on top and back blurb block.", "front_top", "front_bottom", "if_spine_wide", "upper_middle", [0.55, 1.95, 7.1, 4.7], [0.6, 0.6, 2.0, 1.2], "solid"),
    CoverLayoutPreset("center_title_spine_if_room", "Centered Title", "Centered title with optional spine text when wide enough.", "auto", "front_bottom", "if_spine_wide", "lower_middle", [0.6, 2.1, 7.0, 4.5], [0.6, 0.6, 2.0, 1.2], "style_blur"),
    CoverLayoutPreset("lower_title_author_top", "Lower Title", "Title near bottom and author near top for dramatic art focus.", "front_bottom", "front_top", "if_spine_wide", "upper_middle", [0.55, 1.9, 7.1, 4.7], [0.6, 0.7, 2.0, 1.2], "style_blur"),
    CoverLayoutPreset("minimal_top_author_bottom", "Minimal Top", "Minimal typographic treatment with clean back panel.", "front_top", "front_bottom", "if_spine_wide", "center", [0.7, 2.0, 6.8, 4.5], [0.7, 0.6, 2.0, 1.2], "solid"),
    CoverLayoutPreset("imprint_auto_title_safe", "Imprint Auto Title Safe", "Busyness-aware title placement with safe subtitle/blurb handling for premium covers.", "auto", "front_bottom", "if_spine_wide", "upper_middle", [0.6, 2.0, 6.9, 4.4], [0.6, 0.6, 2.0, 1.2], "style_blur"),
]


def presets_payload() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "interior_layout_presets": [asdict(p) for p in INTERIOR_LAYOUT_PRESETS],
        "typography_presets": [asdict(p) for p in TYPOGRAPHY_PRESETS],
        "cover_layout_presets": [asdict(p) for p in COVER_LAYOUT_PRESETS],
    }


def get_preset(preset_id: str, group: str) -> Dict[str, Any]:
    mapping = {
        "interior": {p.id: asdict(p) for p in INTERIOR_LAYOUT_PRESETS},
        "typography": {p.id: asdict(p) for p in TYPOGRAPHY_PRESETS},
        "cover": {p.id: asdict(p) for p in COVER_LAYOUT_PRESETS},
    }
    selected = mapping[group].get(preset_id)
    if not selected:
        raise RuntimeError(f"Unknown {group} preset: {preset_id}")
    return selected
