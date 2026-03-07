from __future__ import annotations

from bookforge.page_architecture.types import ArchitectureType, ArchitectureVariant, Zone, ZoneConstraints, ZoneType


def _z(zone_id: str, zone_type: ZoneType, x: float, y: float, w: float, h: float, safe_only: bool = True) -> Zone:
    return Zone(zone_id=zone_id, zone_type=zone_type, x=x, y=y, w=w, h=h, constraints=ZoneConstraints(min_w=0.08, min_h=0.08, safe_only=safe_only, can_overlap=False))


def architecture_templates() -> list[ArchitectureVariant]:
    return [
        ArchitectureVariant("full_bleed_spread_main", ArchitectureType.FULL_BLEED_SPREAD, [_z("art", ZoneType.ART, 0.0, 0.0, 1.0, 1.0, safe_only=False), _z("caption", ZoneType.CAPTION, 0.06, 0.82, 0.88, 0.12)], ["climax", "wordless"]),
        ArchitectureVariant("full_bleed_single_caption", ArchitectureType.FULL_BLEED_SINGLE, [_z("art", ZoneType.ART, 0.0, 0.0, 1.0, 1.0, safe_only=False), _z("text", ZoneType.TEXT, 0.08, 0.78, 0.84, 0.14)], ["opening", "rising_action"]),
        ArchitectureVariant("vignette_centered", ArchitectureType.VIGNETTE, [_z("art", ZoneType.ART, 0.18, 0.2, 0.64, 0.55), _z("text", ZoneType.TEXT, 0.14, 0.78, 0.72, 0.14)], ["falling_action", "resolution"]),
        ArchitectureVariant("spot_illustration_low_text", ArchitectureType.SPOT_ILLUSTRATION, [_z("art", ZoneType.ART, 0.22, 0.32, 0.56, 0.42), _z("text", ZoneType.TEXT, 0.10, 0.1, 0.80, 0.16)], ["resolution", "calm"]),
        ArchitectureVariant("panel_sequence_triptych", ArchitectureType.PANEL_SEQUENCE, [_z("panel_left", ZoneType.ART, 0.04, 0.1, 0.29, 0.6), _z("panel_mid", ZoneType.ART, 0.355, 0.1, 0.29, 0.6), _z("panel_right", ZoneType.ART, 0.67, 0.1, 0.29, 0.6), _z("caption", ZoneType.CAPTION, 0.08, 0.76, 0.84, 0.14)], ["rising_action", "kinetic"]),
        ArchitectureVariant("wordless_spread_hero", ArchitectureType.WORDLESS_SPREAD, [_z("art", ZoneType.ART, 0.0, 0.0, 1.0, 1.0, safe_only=False), _z("bleed_guard", ZoneType.BLEED_GUARD, 0.0, 0.0, 1.0, 1.0, safe_only=False)], ["climax", "silent"]),
        ArchitectureVariant("text_dominant_story", ArchitectureType.TEXT_DOMINANT, [_z("text", ZoneType.TEXT, 0.08, 0.08, 0.84, 0.38), _z("art", ZoneType.ART, 0.08, 0.50, 0.84, 0.38)], ["opening", "resolution"]),
        ArchitectureVariant("inset_composite_stack", ArchitectureType.INSET_COMPOSITE, [_z("art_base", ZoneType.ART, 0.04, 0.04, 0.92, 0.92), _z("inset_top", ZoneType.INSET, 0.58, 0.12, 0.30, 0.24), _z("inset_bottom", ZoneType.INSET, 0.12, 0.62, 0.28, 0.22), _z("text", ZoneType.TEXT, 0.08, 0.80, 0.84, 0.14)], ["rising_action", "mystery"]),
    ]
