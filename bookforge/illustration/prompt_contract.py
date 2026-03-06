from __future__ import annotations

from typing import Any, Dict, List


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
) -> Dict[str, Any]:
    pvc = lock.get("premium_visual_contract", {})
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
    ]

    flexible = [
        *[f"Nostalgia motif hint: {x}" for x in pvc.get("nostalgia_background_motifs", [])],
        *[f"Art-bible motif: {x}" for x in pvc.get("manuscript_art_bible", {}).get("parallel_visual_motifs", [])],
    ]

    seed = int(lock.get("seeds", {}).get("per_page_seed", {}).get(str(page_number), 0))
    negative_parts = pvc.get("negative_prompt_rules", []) or [lock.get("locked_negative_prompt", "")]

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
        },
    }


def build_prompt_contract(parsed: Dict[str, Any], lock: Dict[str, Any], spread_pairs: List[List[int]] | None = None) -> Dict[str, Any]:
    pages = parsed.get("pages", [])
    total = len(pages)
    spread_set = {tuple(pair) for pair in (spread_pairs or [])}
    objects: List[Dict[str, Any]] = []

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
        objects.append(build_prompt_object(page=p, page_number=no, page_count=total, lock=lock, page_type=page_type, spread_pair=pair, anti_drift_reference=anti_drift))

    cover_context = {"page_number": 0, "text": parsed.get("title", ""), "illustration_notes": "Cover art only; no rendered text."}
    objects.append(build_prompt_object(page=cover_context, page_number=0, page_count=total, lock=lock, page_type="front_cover"))
    objects.append(build_prompt_object(page=cover_context, page_number=total + 1, page_count=total, lock=lock, page_type="back_cover"))

    return {"version": "premium_prompt_contract_v1", "objects": objects}
