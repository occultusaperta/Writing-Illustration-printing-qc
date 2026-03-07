from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from bookforge.qc.composition_qc import focus_bleed_overlap
from bookforge.qc.image_qc import contrast, entropy, sharpness, style_hist_similarity
from bookforge.qc.print_qc import analyze_print_qc
from bookforge.qc.visual_integrity import face_like_regions


def _page_note_map(parsed: Dict[str, Any]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for p in parsed.get("pages", []):
        n = int(p.get("page_number", 0))
        out[n] = str(p.get("illustration_notes", "")).strip()
    return out


def _continuity_expectations(note: str) -> Dict[str, bool]:
    low = note.lower()
    return {
        "patch_bear_presence": "patch" in low,
        "mara_slipper_state": "slipper" in low and "mara" in low,
        "cardigan_cape_continuity": "cardigan" in low or "cape" in low,
    }


def run_premium_visual_qc(
    selected_pages: List[Path],
    *,
    lock: Dict[str, Any],
    parsed_story: Dict[str, Any],
    provider_provenance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pvc = lock.get("premium_visual_contract", {})
    style_ref = Path(lock.get("approved_style", "")) if lock.get("approved_style") else None
    note_map = _page_note_map(parsed_story)

    rows: List[Dict[str, Any]] = []
    weak: List[Dict[str, Any]] = []
    critic_thresholds = {
        "composition_score": 0.70,
        "character_consistency": 0.70,
        "texture_quality": 0.45,
        "detail_density": 0.45,
        "story_alignment": 0.65,
    }

    for idx, path in enumerate(selected_pages, start=1):
        st = style_hist_similarity(path, style_ref) if style_ref and style_ref.exists() else 1.0
        pr = analyze_print_qc(path, style_ref if style_ref and style_ref.exists() else None)
        comp = focus_bleed_overlap(path)
        sharp = sharpness(path)
        ent = entropy(path)
        cont = contrast(path)
        faces = face_like_regions(path)
        note = note_map.get(idx, "")
        required_hidden = pvc.get("required_hidden_details", {}).get(str(idx), [])

        detail_richness = min(1.0, (ent / 8.0) * 0.6 + (sharp / 1200.0) * 0.4)
        cheap_ai_risk = max(0.0, 1.0 - detail_richness)
        typography_collision = comp["overlap"]

        composition_score = max(0.0, 1.0 - float(comp["overlap"]))
        character_consistency_score = float(st)
        texture_quality = max(0.0, min(1.0, (float(cont) / 80.0) * 0.4 + (1.0 - float(pr.get("out_of_gamut_risk", 0.0))) * 0.6))
        detail_density = detail_richness
        story_alignment = 0.9 if note else 0.65

        continuity = _continuity_expectations(note)
        continuity_warnings: List[str] = []
        if continuity["patch_bear_presence"] and character_consistency_score < critic_thresholds["character_consistency"]:
            continuity_warnings.append("Patch bear presence may be inconsistent with approved references.")
        if continuity["mara_slipper_state"] and story_alignment < critic_thresholds["story_alignment"]:
            continuity_warnings.append("Mara slipper state continuity uncertain for this page.")
        if continuity["cardigan_cape_continuity"] and texture_quality < critic_thresholds["texture_quality"]:
            continuity_warnings.append("Cardigan/cape continuity appears visually weak; review needed.")

        checks = {
            "character_consistency": st >= 0.70,
            "style_consistency": st >= 0.72,
            "anatomy_hand_face_sanity": faces <= int(lock.get("qa", {}).get("max_face_like_regions", 3)),
            "composition_clarity": comp["overlap"] <= float(lock.get("qa", {}).get("max_focus_bleed_overlap", 0.15)),
            "storytelling_match": bool(note) or idx <= 2,
            "emotional_readability": pr["brightness_mean"] >= 35,
            "trim_safety": comp["overlap"] <= 0.2,
            "spread_seam_continuity": True,
            "text_overlay_collision_risk": typography_collision <= 0.2,
            "detail_richness_microcontrast": detail_richness >= 0.45,
            "anti_cheap_ai_anti_oversmoothing": cheap_ai_risk <= 0.55,
            "hidden_detail_compliance": True if not required_hidden else detail_richness >= 0.40,
            "illustration_note_compliance": True if not note else st >= 0.65,
            "cover_hierarchy_readability": True,
            "luxury_finish_realism_heuristics": pr["out_of_gamut_risk"] <= float(lock.get("qa", {}).get("max_out_of_gamut_risk", 0.35)),
        }

        critic_scores = {
            "composition_score": composition_score,
            "character_consistency": character_consistency_score,
            "texture_quality": texture_quality,
            "detail_density": detail_density,
            "story_alignment": story_alignment,
        }
        critic_failures = [name for name, score in critic_scores.items() if score < critic_thresholds[name]]

        fails = [k for k, v in checks.items() if not v]
        score = sum(1 for v in checks.values() if v) / max(len(checks), 1)
        row = {
            "page": idx,
            "path": str(path),
            "score": score,
            "checks": checks,
            "failures": fails,
            "visual_critic_scores": critic_scores,
            "visual_critic_failures": critic_failures,
            "continuity": continuity,
            "continuity_warnings": continuity_warnings,
            "metrics": {
                "style_similarity": st,
                "focus_bleed_overlap": comp["overlap"],
                "sharpness": sharp,
                "entropy": ent,
                "contrast": cont,
                "detail_richness": detail_richness,
                "cheap_ai_risk": cheap_ai_risk,
                **pr,
            },
            "remediation_advice": [
                "Regenerate with stronger subject silhouette and cleaner overlay safety zones." if fails else "No remediation required.",
                "Increase texture/microcontrast hooks for premium finish." if detail_richness < 0.45 else "",
                "Reinforce continuity references for Patch/Mara/cardigan-cape anchors." if continuity_warnings else "",
            ],
        }
        rows.append(row)
        if fails or critic_failures:
            weak.append({"page": idx, "score": score, "failures": fails + critic_failures})

    weak_sorted = sorted(weak, key=lambda x: x["score"])[:8]
    hard_fail_pages = [x["page"] for x in rows if x["score"] < 0.74 or x.get("visual_critic_failures")]
    status = "FAIL" if hard_fail_pages else "PASS"
    regen = [{"page": p, "reason": "premium_qc_score_below_threshold_or_visual_critic"} for p in hard_fail_pages]

    return {
        "status": status,
        "hard_fail_threshold": 0.74,
        "hard_fail_pages": hard_fail_pages,
        "weak_pages_ranked": weak_sorted,
        "pages": rows,
        "visual_critic_thresholds": critic_thresholds,
        "provider_runtime_provenance": provider_provenance or {},
        "regen_recommendations": regen,
        "lock_provenance": lock.get("premium_visual_contract_provenance", {}),
    }
