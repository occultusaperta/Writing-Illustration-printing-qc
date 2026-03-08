from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple

from bookforge.layout_search.types import LayoutPermutation, LayoutSearchConfig



def _round_zone(zone: Dict[str, float]) -> Dict[str, float]:
    return {k: round(float(zone.get(k, 0.0)), 4) for k in ("x", "y", "w", "h")}


def _clamp_zone(zone: Dict[str, float]) -> Dict[str, float]:
    x = max(0.0, min(0.96, float(zone.get("x", 0.08))))
    y = max(0.0, min(0.96, float(zone.get("y", 0.06))))
    w = max(0.04, min(1.0 - x, float(zone.get("w", 0.84))))
    h = max(0.04, min(1.0 - y, float(zone.get("h", 0.22))))
    return _round_zone({"x": x, "y": y, "w": w, "h": h})


def _shift_zone(zone: Dict[str, float], dx: float, dy: float, dw: float = 0.0, dh: float = 0.0) -> Dict[str, float]:
    return _clamp_zone(
        {
            "x": float(zone.get("x", 0.0)) + dx,
            "y": float(zone.get("y", 0.0)) + dy,
            "w": float(zone.get("w", 0.0)) + dw,
            "h": float(zone.get("h", 0.0)) + dh,
        }
    )


def _swap_orientation(zone: Dict[str, float], position: str) -> Dict[str, float]:
    if position == "top":
        return _clamp_zone({"x": 0.08, "y": 0.06, "w": 0.84, "h": max(0.14, zone.get("h", 0.2))})
    if position == "bottom":
        return _clamp_zone({"x": 0.08, "y": 0.70, "w": 0.84, "h": max(0.14, zone.get("h", 0.2))})
    if position == "left":
        return _clamp_zone({"x": 0.06, "y": 0.18, "w": 0.38, "h": 0.68})
    return _clamp_zone({"x": 0.56, "y": 0.18, "w": 0.38, "h": 0.68})


def _zone_fingerprint(text_zone: Dict[str, float], art_zone: Dict[str, float]) -> Tuple[float, ...]:
    tz = _round_zone(text_zone)
    az = _round_zone(art_zone)
    return (tz["x"], tz["y"], tz["w"], tz["h"], az["x"], az["y"], az["w"], az["h"])


def generate_layout_permutations(
    *,
    page_numbers: Sequence[int],
    base_layout: Dict[str, Any],
    config: LayoutSearchConfig,
    seed: int,
    is_spread: bool,
    variant_candidates: Sequence[Dict[str, Any]] | None = None,
) -> List[LayoutPermutation]:
    cap = config.max_permutations_per_spread if is_spread else config.max_permutations_per_page
    cap = max(1, cap)
    rng = random.Random(seed)

    text_zone = _clamp_zone(base_layout.get("text_zone", {"x": 0.08, "y": 0.06, "w": 0.84, "h": 0.22}))
    art_zone = _clamp_zone(base_layout.get("art_zone", {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}))

    candidates: List[LayoutPermutation] = []
    seen: set[Tuple[float, ...]] = set()

    def _append(pid: str, tz: Dict[str, float], az: Dict[str, float], notes: List[str], override: Dict[str, Any] | None = None) -> None:
        fp = _zone_fingerprint(tz, az)
        if fp in seen:
            return
        seen.add(fp)
        row = dict(base_layout)
        if override:
            row.update(override)
        candidates.append(
            LayoutPermutation(
                permutation_id=pid,
                page_numbers=tuple(int(x) for x in page_numbers),
                architecture_type=str(row.get("architecture_type", "none")),
                variant_id=str(row.get("variant_id", "")),
                text_zone=_round_zone(tz),
                art_zone=_round_zone(az),
                panel_zones=[dict(z) for z in row.get("panel_zones", []) if isinstance(z, dict)],
                inset_zones=[dict(z) for z in row.get("inset_zones", []) if isinstance(z, dict)],
                reserve_whitespace=[dict(z) for z in row.get("reserve_whitespace", []) if isinstance(z, dict)],
                compositor_hints=dict(row.get("compositor_hints", {})),
                notes=notes,
            )
        )

    _append("base", text_zone, art_zone, ["base_layout"])

    if config.enable_text_zone_variation:
        for pos in ("top", "bottom", "left", "right"):
            _append(f"tz_{pos}", _swap_orientation(text_zone, pos), art_zone, [f"text_zone_{pos}"])
        # stronger practical span/position variation while bounded.
        text_variants = [
            ("tz_tighter", 0.02, 0.01, -0.08, -0.04),
            ("tz_wider", -0.02, -0.01, 0.10, 0.04),
            ("tz_hero_top", 0.0, -0.03, 0.02, 0.0),
            ("tz_banner_bottom", 0.0, 0.04, 0.04, -0.01),
            ("tz_left_column", -0.05, 0.0, -0.30, 0.10),
            ("tz_right_column", 0.17, 0.0, -0.30, 0.10),
        ]
        for pid, dx, dy, dw, dh in text_variants:
            _append(pid, _shift_zone(text_zone, dx, dy, dw, dh), art_zone, [pid])

    if config.enable_crop_shift:
        # stronger crop/placement perturbations with bounded cardinal set.
        for dx, dy, dw, dh, name in [
            (-0.08, 0.0, 0.0, 0.0, "crop_shift_left"),
            (0.08, 0.0, 0.0, 0.0, "crop_shift_right"),
            (0.0, -0.06, 0.0, 0.0, "crop_shift_up"),
            (0.0, 0.06, 0.0, 0.0, "crop_shift_down"),
            (-0.04, -0.03, 0.05, 0.05, "crop_zoom_out_ul"),
            (0.03, 0.03, -0.05, -0.05, "crop_zoom_in_lr"),
        ]:
            _append(name, text_zone, _shift_zone(art_zone, dx, dy, dw, dh), ["crop_shift", name])

    if config.enable_variant_swap_within_architecture and variant_candidates:
        for idx, variant in enumerate(variant_candidates[:4], start=1):
            tz = _clamp_zone(variant.get("text_zone", text_zone))
            az = _clamp_zone(variant.get("art_zone", art_zone))
            _append(
                f"variant_swap_{idx}",
                tz,
                az,
                ["variant_swap_within_architecture"],
                {"variant_id": variant.get("variant_id", base_layout.get("variant_id", ""))},
            )

    # deterministic bounded shuffle to avoid repeated ordering bias while preserving reproducibility.
    keys = list(range(len(candidates)))
    rng.shuffle(keys)
    bounded = [candidates[i] for i in keys[:cap]]
    if not any(c.permutation_id == "base" for c in bounded):
        bounded[-1] = next(c for c in candidates if c.permutation_id == "base")
    return bounded
