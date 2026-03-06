from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class LockValidationResult:
    ok: bool
    missing: List[str]
    warnings: List[str]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_visual_lock(lock: Dict[str, Any], parsed_story: Dict[str, Any] | None = None, approval: Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Normalize old/new lock payloads into premium_visual_contract.

    Returns: (normalized_lock, provenance)
    """
    parsed_story = parsed_story or {}
    approval = approval or {}
    visual = dict(lock.get("visual_lock", {}))
    pages = parsed_story.get("pages", []) if isinstance(parsed_story.get("pages"), list) else []
    spreads = lock.get("spreads", {}) if isinstance(lock.get("spreads"), dict) else {}

    contract = {
        "approved_variant_id": int(lock.get("approved_variant", visual.get("variant_id", 1) or 1)),
        "character_reference_pack": {
            "primary": str(lock.get("approved_character", visual.get("character_reference", ""))),
            "turnaround": _as_list(visual.get("turnaround", [])),
            "expressions": _as_list(visual.get("expressions", [])),
        },
        "style_reference_pack": {
            "primary": str(lock.get("approved_style", visual.get("style_reference", ""))),
            "cover": str(lock.get("approved_cover", visual.get("cover_reference", ""))),
            "palette_refs": _as_list(visual.get("palette_refs", [])),
        },
        "palette_lock": lock.get("style_bible", {}).get("palette", []),
        "lighting_lock": visual.get("lighting_lock", "soft cinematic child-safe keylight"),
        "composition_lock": visual.get("composition_lock", "clear focal subject; avoid clutter at trim-safe zones"),
        "lens_framing_cues": _as_list(visual.get("lens_framing_cues", ["child-eye-level camera", "storybook focal depth"])),
        "texture_finish_cues": _as_list(visual.get("texture_finish_cues", ["premium print-friendly texture", "microcontrast retained"])),
        "negative_prompt_rules": _as_list(lock.get("locked_negative_prompt", "")),
        "deterministic_seed_strategy": {
            "base_seed": int(lock.get("seeds", {}).get("base_seed", 0)),
            "per_page_seed": {str(k): int(v) for k, v in (lock.get("seeds", {}).get("per_page_seed", {}) or {}).items()},
            "formula": "base + page*101 + variant_offset",
        },
        "spread_rules": {
            "mode": spreads.get("mode", "none"),
            "pairs": spreads.get("pairs", []),
            "seam_continuity": True,
        },
        "trim_typography_safe_rules": {
            "trim_safe_in": float(lock.get("print", {}).get("safe_in", 0.25)),
            "text_overlay_safe": "no focal faces/hands in caption strip; preserve top-title area",
        },
        "storyweaver_illustration_note_constraints": [
            {
                "page_number": int(p.get("page_number", idx + 1)),
                "note": str(p.get("illustration_notes", "")).strip(),
            }
            for idx, p in enumerate(pages)
            if str(p.get("illustration_notes", "")).strip()
        ],
        "required_hidden_details": {
            str(p.get("page_number", idx + 1)): [str(x).strip() for x in p.get("required_hidden_details", []) if str(x).strip()]
            for idx, p in enumerate(pages)
            if p.get("required_hidden_details")
        },
        "cover_specific_rules": {
            "hierarchy": "title > character silhouette > subtitle > author",
            "barcode_safe_box_in": lock.get("cover", {}).get("barcode_box_in", [0.6, 0.6, 2.0, 1.2]),
            "title_safe": True,
        },
        "nostalgia_background_motifs": _as_list(visual.get("nostalgia_background_motifs", [])),
        "character_design_constraints": _as_list(visual.get("character_design_constraints", approval.get("character_design_constraints", []))),
        "manuscript_art_bible": {
            "child_perspective_camera_height": approval.get("child_perspective_camera_height", "eye-level"),
            "recurring_easter_eggs": _as_list(approval.get("recurring_easter_eggs", [])),
            "character_proportion_rules": _as_list(approval.get("character_proportion_rules", [])),
            "emotional_warmth_shift": _as_list(approval.get("emotional_warmth_shift", [])),
            "repeated_prop_continuity": _as_list(approval.get("repeated_prop_continuity", [])),
            "parallel_visual_motifs": _as_list(approval.get("parallel_visual_motifs", [])),
            "quiet_section_visual_deceleration": _as_list(approval.get("quiet_section_visual_deceleration", [])),
            "full_spread_comic_reveal_logic": _as_list(approval.get("full_spread_comic_reveal_logic", [])),
        },
    }

    lock["premium_visual_contract"] = contract
    lock["visual_lock"] = {
        "variant_id": contract["approved_variant_id"],
        "character_reference": contract["character_reference_pack"]["primary"],
        "style_reference": contract["style_reference_pack"]["primary"],
        "cover_reference": contract["style_reference_pack"]["cover"],
    }

    provenance = {
        "applied_fields": sorted([k for k, v in contract.items() if v not in (None, "", [], {})]),
        "source": {
            "lock": True,
            "approval": bool(approval),
            "story": bool(parsed_story),
        },
    }
    lock["premium_visual_contract_provenance"] = provenance
    return lock, provenance


def validate_visual_lock(lock: Dict[str, Any], *, require_lock: bool = False) -> LockValidationResult:
    required = [
        "approved_variant",
        "approved_character",
        "approved_style",
        "locked_prompt_prefix",
        "locked_negative_prompt",
        "storyboard",
        "print",
        "fal",
        "qa",
        "seeds",
    ]
    missing = [k for k in required if k not in lock]
    warnings: List[str] = []
    pvc = lock.get("premium_visual_contract", {})
    if pvc and not pvc.get("storyweaver_illustration_note_constraints"):
        warnings.append("premium_visual_contract has no illustration-note constraints")
    if pvc and not pvc.get("deterministic_seed_strategy", {}).get("per_page_seed"):
        warnings.append("premium_visual_contract deterministic_seed_strategy missing per_page_seed")

    ok = not missing or not require_lock
    return LockValidationResult(ok=ok, missing=missing, warnings=warnings)


def ensure_reference_paths_exist(lock: Dict[str, Any]) -> None:
    for key in ["approved_character", "approved_style", "approved_cover"]:
        path = lock.get(key)
        if path and not Path(path).exists():
            raise RuntimeError(f"LOCK reference missing: {key} -> {path}")
