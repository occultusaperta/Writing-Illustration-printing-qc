from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Tuple

from bookforge.layout_search.types import LayoutPermutation, LayoutSearchConfig


def _clamp_zone(zone: Dict[str, float]) -> Dict[str, float]:
    x = max(0.0, min(0.96, float(zone.get("x", 0.08))))
    y = max(0.0, min(0.96, float(zone.get("y", 0.06))))
    w = max(0.04, min(1.0 - x, float(zone.get("w", 0.84))))
    h = max(0.04, min(1.0 - y, float(zone.get("h", 0.22))))
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


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
        return _clamp_zone({"x": 0.08, "y": 0.06, "w": 0.84, "h": max(0.12, zone.get("h", 0.2))})
    if position == "bottom":
        return _clamp_zone({"x": 0.08, "y": 0.72, "w": 0.84, "h": max(0.12, zone.get("h", 0.2))})
    if position == "left":
        return _clamp_zone({"x": 0.06, "y": 0.22, "w": 0.36, "h": 0.62})
    return _clamp_zone({"x": 0.58, "y": 0.22, "w": 0.36, "h": 0.62})


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

    def _append(pid: str, tz: Dict[str, float], az: Dict[str, float], notes: List[str], override: Dict[str, Any] | None = None) -> None:
        row = dict(base_layout)
        if override:
            row.update(override)
        candidates.append(
            LayoutPermutation(
                permutation_id=pid,
                page_numbers=tuple(int(x) for x in page_numbers),
                architecture_type=str(row.get("architecture_type", "none")),
                variant_id=str(row.get("variant_id", "")),
                text_zone=tz,
                art_zone=az,
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
        _append("tz_tighter", _shift_zone(text_zone, 0.02, 0.01, -0.06, -0.02), art_zone, ["text_zone_tighter"])
        _append("tz_wider", _shift_zone(text_zone, -0.02, -0.01, 0.08, 0.03), art_zone, ["text_zone_wider"])

    if config.enable_crop_shift:
        for dx, dy in [(-0.04, 0.0), (0.04, 0.0), (0.0, -0.03), (0.0, 0.03)]:
            _append(f"crop_shift_{dx:.2f}_{dy:.2f}", text_zone, _shift_zone(art_zone, dx, dy), ["crop_shift"])

    if config.enable_variant_swap_within_architecture and variant_candidates:
        for idx, variant in enumerate(variant_candidates[:3], start=1):
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
        bounded[-1] = candidates[0]
    return bounded
