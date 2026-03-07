from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple

from bookforge.page_architecture.types import ArchitectureType


@dataclass(frozen=True)
class NormalizedRect:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class AppliedLayoutInstruction:
    page_number: int
    architecture_type: str
    variant_id: str
    page_side: str
    spread_mode: bool
    art_zone: NormalizedRect
    text_zone: NormalizedRect
    panel_zones: Tuple[NormalizedRect, ...]
    inset_zones: Tuple[NormalizedRect, ...]
    reserve_whitespace: Tuple[NormalizedRect, ...]
    allow_text_overlay: bool
    suppress_body_text: bool
    gutter_sensitive: bool
    gutter_safe_applied: bool
    layout_fallback_reason: str
    compositor_hints: Dict[str, Any]


FULL_PAGE = NormalizedRect(0.0, 0.0, 1.0, 1.0)
SAFE_CENTER = NormalizedRect(0.1, 0.78, 0.8, 0.14)


def _clamp_rect(rect: Dict[str, Any] | NormalizedRect | None, default: NormalizedRect) -> NormalizedRect:
    if isinstance(rect, NormalizedRect):
        return rect
    if not isinstance(rect, dict):
        return default
    x = max(0.0, min(1.0, float(rect.get("x", default.x))))
    y = max(0.0, min(1.0, float(rect.get("y", default.y))))
    w = max(0.02, min(1.0 - x, float(rect.get("w", default.w))))
    h = max(0.02, min(1.0 - y, float(rect.get("h", default.h))))
    return NormalizedRect(x, y, w, h)


def _zone(variant: Dict[str, Any], zone_id: str, fallback: NormalizedRect) -> NormalizedRect:
    zones = variant.get("zones", []) if isinstance(variant, dict) else []
    for z in zones:
        if isinstance(z, dict) and str(z.get("zone_id", "")) == zone_id:
            return _clamp_rect(z, fallback)
    return fallback


def _zones_by_type(variant: Dict[str, Any], zone_type: str) -> List[NormalizedRect]:
    zones = variant.get("zones", []) if isinstance(variant, dict) else []
    out: List[NormalizedRect] = []
    for z in zones:
        if isinstance(z, dict) and str(z.get("zone_type", "")) == zone_type:
            out.append(_clamp_rect(z, FULL_PAGE))
    return out


def _is_spread_page(page_number: int, spread_pairs: List[Tuple[int, int]]) -> bool:
    return any(page_number in pair for pair in spread_pairs)


def build_layout_application_map(
    pages: List[Dict[str, Any]],
    architecture_plan: List[Dict[str, Any]] | None,
    variants_by_id: Dict[str, Dict[str, Any]],
    spread_pairs: List[Tuple[int, int]],
) -> Dict[int, Dict[str, Any]]:
    plan_items = architecture_plan if isinstance(architecture_plan, list) else []
    plan_by_page = {int(p.get("page_number", 0)): p for p in plan_items if isinstance(p, dict)}

    applied: Dict[int, Dict[str, Any]] = {}
    for page in pages:
        page_no = int(page.get("page_number", 0) or 0)
        if page_no <= 0:
            continue
        plan = plan_by_page.get(page_no)
        if not plan:
            applied[page_no] = asdict(
                AppliedLayoutInstruction(
                    page_number=page_no,
                    architecture_type="none",
                    variant_id="",
                    page_side="recto" if page_no % 2 else "verso",
                    spread_mode=False,
                    art_zone=FULL_PAGE,
                    text_zone=SAFE_CENTER,
                    panel_zones=(),
                    inset_zones=(),
                    reserve_whitespace=(),
                    allow_text_overlay=False,
                    suppress_body_text=False,
                    gutter_sensitive=False,
                    gutter_safe_applied=False,
                    layout_fallback_reason="architecture_plan_missing",
                    compositor_hints={"mode": "legacy_default"},
                )
            )
            continue

        variant_id = str(plan.get("selected_variant_id", ""))
        variant = variants_by_id.get(variant_id, {})
        arch_type = str(plan.get("selected_architecture_type", ""))
        page_side = "recto" if page_no % 2 else "verso"
        spread_mode = _is_spread_page(page_no, spread_pairs)
        instruction = _apply_architecture(page_no, page_side, spread_mode, arch_type, variant_id, variant)
        applied[page_no] = asdict(instruction)
    return applied


def _apply_architecture(
    page_number: int,
    page_side: str,
    spread_mode: bool,
    architecture_type: str,
    variant_id: str,
    variant: Dict[str, Any],
) -> AppliedLayoutInstruction:
    fallback = ""
    gutter_sensitive = architecture_type in {ArchitectureType.FULL_BLEED_SPREAD.value, ArchitectureType.WORDLESS_SPREAD.value}
    gutter_safe_applied = not gutter_sensitive

    art_zone = _zone(variant, "art", FULL_PAGE)
    text_zone = _zone(variant, "text", _zone(variant, "caption", SAFE_CENTER))
    panel_zones = tuple(_zones_by_type(variant, "art"))
    inset_zones = tuple(_zones_by_type(variant, "inset"))
    whitespace: Tuple[NormalizedRect, ...] = ()
    allow_overlay = False
    suppress = False
    hints: Dict[str, Any] = {"mode": "legacy_default"}

    if architecture_type == ArchitectureType.FULL_BLEED_SPREAD.value:
        allow_overlay = True
        gutter_safe_applied = True
        hints = {"mode": "full_bleed_spread", "gutter_guard": True, "full_bleed": True}
    elif architecture_type == ArchitectureType.FULL_BLEED_SINGLE.value:
        # art on recto; text-heavy layout on facing verso.
        if page_side == "recto":
            suppress = True
            hints = {"mode": "full_bleed_single_art_page", "full_bleed": True, "facing_behavior": "art_page"}
        else:
            art_zone = NormalizedRect(0.12, 0.08, 0.76, 0.42)
            text_zone = NormalizedRect(0.10, 0.54, 0.80, 0.36)
            hints = {"mode": "full_bleed_single_text_page", "facing_behavior": "text_page"}
    elif architecture_type == ArchitectureType.VIGNETTE.value:
        art_zone = _zone(variant, "art", NormalizedRect(0.2, 0.2, 0.6, 0.5))
        text_zone = _zone(variant, "text", NormalizedRect(0.14, 0.78, 0.72, 0.14))
        whitespace = (NormalizedRect(0.05, 0.05, 0.9, 0.14),)
        hints = {"mode": "vignette", "preserve_whitespace": True}
    elif architecture_type == ArchitectureType.SPOT_ILLUSTRATION.value:
        art_zone = _zone(variant, "art", NormalizedRect(0.26, 0.30, 0.48, 0.38))
        text_zone = _zone(variant, "text", NormalizedRect(0.10, 0.10, 0.80, 0.16))
        whitespace = (NormalizedRect(0.08, 0.54, 0.84, 0.36),)
        hints = {"mode": "spot_illustration", "spot_scale": 0.55}
    elif architecture_type == ArchitectureType.PANEL_SEQUENCE.value:
        panels = panel_zones[:3] if len(panel_zones) >= 3 else (
            NormalizedRect(0.05, 0.12, 0.27, 0.56),
            NormalizedRect(0.365, 0.12, 0.27, 0.56),
            NormalizedRect(0.68, 0.12, 0.27, 0.56),
        )
        panel_zones = tuple(panels)
        text_zone = _zone(variant, "caption", NormalizedRect(0.08, 0.76, 0.84, 0.14))
        art_zone = FULL_PAGE
        hints = {"mode": "panel_sequence", "panel_count": len(panel_zones)}
    elif architecture_type == ArchitectureType.WORDLESS_SPREAD.value:
        suppress = True
        allow_overlay = False
        gutter_safe_applied = True
        text_zone = SAFE_CENTER
        hints = {"mode": "wordless_spread", "body_text": "suppressed", "full_bleed": True, "gutter_guard": True}
    elif architecture_type == ArchitectureType.TEXT_DOMINANT.value:
        text_zone = _zone(variant, "text", NormalizedRect(0.08, 0.08, 0.84, 0.42))
        art_zone = _zone(variant, "art", NormalizedRect(0.08, 0.56, 0.84, 0.30))
        hints = {"mode": "text_dominant", "text_priority": "high"}
    elif architecture_type == ArchitectureType.INSET_COMPOSITE.value:
        base = _zone(variant, "art_base", FULL_PAGE)
        art_zone = base
        inset_zones = tuple(_zones_by_type(variant, "inset")) or (
            NormalizedRect(0.62, 0.12, 0.26, 0.22),
            NormalizedRect(0.12, 0.64, 0.24, 0.20),
        )
        text_zone = _zone(variant, "text", NormalizedRect(0.08, 0.80, 0.84, 0.14))
        allow_overlay = True
        hints = {"mode": "inset_composite", "inset_border": True, "inset_shadow": True}
    else:
        fallback = f"unsupported_architecture_type:{architecture_type or 'unknown'}"

    if gutter_sensitive and not spread_mode:
        gutter_safe_applied = False
        fallback = fallback or "spread_architecture_without_spread_pair"

    return AppliedLayoutInstruction(
        page_number=page_number,
        architecture_type=architecture_type or "none",
        variant_id=variant_id,
        page_side=page_side,
        spread_mode=spread_mode,
        art_zone=art_zone,
        text_zone=text_zone,
        panel_zones=panel_zones,
        inset_zones=inset_zones,
        reserve_whitespace=whitespace,
        allow_text_overlay=allow_overlay,
        suppress_body_text=suppress,
        gutter_sensitive=gutter_sensitive,
        gutter_safe_applied=gutter_safe_applied,
        layout_fallback_reason=fallback,
        compositor_hints=hints,
    )
