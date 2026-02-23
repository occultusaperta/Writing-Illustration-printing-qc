from __future__ import annotations

from typing import Any, Dict, List

ARTIFACT_TYPES = [
    "hidden_motif",
    "recurring_side_character",
    "background_micro_plot",
    "scavenger_hunt_token",
    "repeated_phrase_call_and_response",
    "visual_foreshadow",
]


def propose_artifact_options(age_band: str, story_cues: Dict[str, Any]) -> Dict[str, Any]:
    motif = story_cues.get("motif", "star")
    side_char = story_cues.get("side_character", "tiny beetle")
    token = story_cues.get("token", "moon")

    plans = []
    for idx, intensity in enumerate(["light", "medium", "high"], start=1):
        sequence = ARTIFACT_TYPES[:] if intensity != "light" else ARTIFACT_TYPES[:4]
        plans.append(
            {
                "plan_id": f"plan_{idx}_{intensity}",
                "name": f"{intensity.title()} micro-engagement",
                "intensity": intensity,
                "notes": f"Subtle, no text/logos, tuned for age {age_band}",
                "artifact_sequence": sequence,
                "defaults": {"motif": motif, "side_character": side_char, "token": token},
            }
        )

    return {"age_band": age_band, "plans": plans, "artifact_types": ARTIFACT_TYPES}


def apply_artifact_plan_to_pages(plan: Dict[str, Any], pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seq = list(plan.get("artifact_sequence", ARTIFACT_TYPES))
    defaults = plan.get("defaults", {})
    out: List[Dict[str, Any]] = []
    for idx, page in enumerate(sorted(pages, key=lambda p: int(p.get("page_number", 0))), start=1):
        a_type = seq[(idx - 1) % len(seq)]
        cue = {
            "hidden_motif": f"Place a tiny {defaults.get('motif', 'star')} in background shapes.",
            "recurring_side_character": f"Include the subtle {defaults.get('side_character', 'tiny sidekick')} watching the scene.",
            "background_micro_plot": "Advance a tiny background event by one step from the previous page.",
            "scavenger_hunt_token": f"Hide one {defaults.get('token', 'token')} for seek-and-find participation.",
            "repeated_phrase_call_and_response": "Stage visual beat to support a repeated read-aloud call-and-response phrase.",
            "visual_foreshadow": "Include a tiny future-story object as foreshadowing near scene edge.",
        }[a_type]
        out.append({"page_number": int(page.get("page_number", idx)), "artifact_type": a_type, "instruction": cue})
    return out
