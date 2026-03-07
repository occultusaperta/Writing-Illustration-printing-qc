from __future__ import annotations

from typing import Any, Dict, List

from bookforge.illustration.composition import compute_golden_ratio_points, compute_rule_of_thirds_grid


def _tone_from_story(page: Dict[str, Any]) -> str:
    text = str(page.get("text", "")).lower()
    if any(w in text for w in ["quiet", "sleep", "soft"]):
        return "gentle-warm"
    if any(w in text for w in ["wow", "surprise", "boom"]):
        return "dramatic-delight"
    return "warm-storybook"


def _intent(page: Dict[str, Any]) -> str:
    txt = str(page.get("text", "")).strip()
    return (txt[:180] + "…") if len(txt) > 180 else txt


def build_prompt_object(
    *,
    page: Dict[str, Any],
    page_number: int,
    page_count: int,
    lock: Dict[str, Any],
    page_type: str,
    spread_pair: List[int] | None = None,
    anti_drift_reference: str = "",
    width: int = 1024,
    height: int = 1024,
    color_script_guidance: Dict[str, Any] | None = None,
    page_architecture_guidance: Dict[str, Any] | None = None,
    planning_prompt_lines: List[str] | None = None,
    planning_negative_lines: List[str] | None = None,
    camera_language_guidance: Dict[str, Any] | None = None,
    hidden_world_guidance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pvc = lock.get("premium_visual_contract", {})
    composition_guidance = pvc.get("composition_guidance", {}) if isinstance(pvc.get("composition_guidance", {}), dict) else {}
    character_proportions = pvc.get("character_proportions", {}) if isinstance(pvc.get("character_proportions", {}), dict) else {}
    thirds = compute_rule_of_thirds_grid(width, height)
    golden = compute_golden_ratio_points(width, height)
    focal_zone = str(composition_guidance.get("focal_zone", "golden_ratio_top_left")).strip() or "golden_ratio_top_left"
    focal_point = golden.get(focal_zone) or thirds.get(focal_zone) or golden["golden_ratio_top_left"]
    secondary_anchor = thirds.get("thirds_bottom_right", focal_point)

    notes = str(page.get("illustration_notes", "")).strip()
    hidden = [str(x).strip() for x in page.get("required_hidden_details", []) if str(x).strip()]

    non_negotiable: List[str] = [
        str(lock.get("locked_prompt_prefix", "")).strip(),
        f"Printed story context (exact): {str(page.get('text', '')).strip()}",
        f"Illustration notes (hard): {notes}" if notes else "",
        f"Hidden details (must include): {'; '.join(hidden)}" if hidden else "",
        "Trim-safe composition; keep focal action inside safe area.",
        "Text overlay safety: keep top and bottom overlay zones uncluttered.",
        f"Character lock: {pvc.get('character_reference_pack', {}).get('primary', lock.get('approved_character', ''))}",
        f"Style lock: {pvc.get('style_reference_pack', {}).get('primary', lock.get('approved_style', ''))}",
        anti_drift_reference,
        f"Composition focal_zone: {focal_zone} @ {focal_point}",
        (
            f"Composition subject_anchor: primary={composition_guidance.get('primary_subject', 'primary')} @ {focal_point}; "
            f"secondary={composition_guidance.get('secondary_subject', '')} @ {secondary_anchor}"
        ),
        f"Composition eye_flow_direction: {composition_guidance.get('eye_flow_direction', 'left_to_right')}",
        f"Camera height: {composition_guidance.get('camera_height', 'child_eye_level')}",
    ]
    if page_type == "spread" and spread_pair:
        non_negotiable.append(f"Generate seamless full-bleed double-page spread for pages {spread_pair[0]}-{spread_pair[1]}.")
    if page_type in {"front_cover", "back_cover"}:
        non_negotiable.append("Respect cover hierarchy and barcode/title safe zones.")

    preferred = [
        f"Emotional tone: {_tone_from_story(page)}",
        f"Storytelling intent: {_intent(page)}",
        "Premium art direction: luxury children's book finish, tactile texture, clear silhouette storytelling.",
        *[f"Lens/framing: {x}" for x in pvc.get("lens_framing_cues", [])],
        *[f"Texture/finish: {x}" for x in pvc.get("texture_finish_cues", [])],
        *[f"Character proportion hint: {k}={v}" for k, v in character_proportions.items()],
        *[str(x).strip() for x in (planning_prompt_lines or []) if str(x).strip()],
    ]

    flexible = [
        *[f"Nostalgia motif hint: {x}" for x in pvc.get("nostalgia_background_motifs", [])],
        *[f"Art-bible motif: {x}" for x in pvc.get("manuscript_art_bible", {}).get("parallel_visual_motifs", [])],
    ]

    seed = int(lock.get("seeds", {}).get("per_page_seed", {}).get(str(page_number), 0))
    negative_parts = pvc.get("negative_prompt_rules", []) or [lock.get("locked_negative_prompt", "")]
    negative_parts.extend([str(x).strip() for x in (planning_negative_lines or []) if str(x).strip()])

    return {
        "page_number": page_number,
        "page_type": page_type,
        "page_count": page_count,
        "hierarchy": {
            "non_negotiable_constraints": [x for x in non_negotiable if x],
            "preferred_style_constraints": [x for x in preferred if x],
            "flexible_embellishments": [x for x in flexible if x],
        },
        "negative_prompt": " ".join([str(x).strip() for x in negative_parts if str(x).strip()]),
        "deterministic_seed": seed,
        "prompt_text": " ".join([x for x in non_negotiable + preferred + flexible if x]),
        "metadata": {
            "character_lock_metadata": pvc.get("character_reference_pack", {}),
            "style_lock_metadata": pvc.get("style_reference_pack", {}),
            "spread_pair": spread_pair or [],
            "trim_typography_safe_rules": pvc.get("trim_typography_safe_rules", {}),
            "composition_guidance": {
                "primary_subject": composition_guidance.get("primary_subject", "Mara"),
                "secondary_subject": composition_guidance.get("secondary_subject", "Patch"),
                "focal_zone": focal_zone,
                "camera_height": composition_guidance.get("camera_height", "child_eye_level"),
                "focal_point": list(focal_point),
                "subject_anchor": {
                    "primary": list(focal_point),
                    "secondary": list(secondary_anchor),
                },
                "eye_flow_direction": composition_guidance.get("eye_flow_direction", "left_to_right"),
                "rule_of_thirds": {k: list(v) for k, v in thirds.items()},
                "golden_ratio_points": {k: list(v) for k, v in golden.items()},
            },
            "character_proportions": character_proportions,
            "reference_images": [
                pvc.get("locked_character_sheet", pvc.get("character_reference_pack", {}).get("primary", "")),
                pvc.get("locked_line_style", pvc.get("style_reference_pack", {}).get("primary", "")),
            ],
            "color_script_guidance": color_script_guidance or {},
            "page_architecture_guidance": page_architecture_guidance or {},
            "camera_language_guidance": camera_language_guidance or {},
            "hidden_world_guidance": hidden_world_guidance or {},
        },
    }


def build_prompt_contract(
    parsed: Dict[str, Any],
    lock: Dict[str, Any],
    spread_pairs: List[List[int]] | None = None,
    planning_guidance: Dict[int, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    pages = parsed.get("pages", [])
    total = len(pages)
    spread_set = {tuple(pair) for pair in (spread_pairs or [])}
    objects: List[Dict[str, Any]] = []

    required_pixels = lock.get("print", {}).get("required_pixels", [1024, 1024])
    width = int(required_pixels[0]) if isinstance(required_pixels, list) and required_pixels else 1024
    height = int(required_pixels[1]) if isinstance(required_pixels, list) and len(required_pixels) > 1 else 1024

    for p in pages:
        no = int(p.get("page_number", 0))
        page_type = "single_page"
        pair = None
        for sp in spread_set:
            if no in sp:
                page_type = "spread"
                pair = [sp[0], sp[1]]
                break
        anti_drift = f"Anti-drift: match approved variant {lock.get('approved_variant')} character silhouette, palette and lighting from lock."
        page_guidance = (planning_guidance or {}).get(no, {}) if planning_guidance else {}
        objects.append(
            build_prompt_object(
                page=p,
                page_number=no,
                page_count=total,
                lock=lock,
                page_type=page_type,
                spread_pair=pair,
                anti_drift_reference=anti_drift,
                width=width,
                height=height,
                color_script_guidance=page_guidance.get("color_script_guidance", {}),
                page_architecture_guidance=page_guidance.get("page_architecture_guidance", {}),
                planning_prompt_lines=page_guidance.get("prompt_lines", []),
                planning_negative_lines=page_guidance.get("negative_lines", []),
                camera_language_guidance=page_guidance.get("camera_language_guidance", {}),
                hidden_world_guidance=page_guidance.get("hidden_world_guidance", {}),
            )
        )

    cover_context = {"page_number": 0, "text": parsed.get("title", ""), "illustration_notes": "Cover art only; no rendered text."}
    objects.append(build_prompt_object(page=cover_context, page_number=0, page_count=total, lock=lock, page_type="front_cover", width=width, height=height))
    objects.append(build_prompt_object(page=cover_context, page_number=total + 1, page_count=total, lock=lock, page_type="back_cover", width=width, height=height))

    return {"version": "premium_prompt_contract_v1", "objects": objects}
