from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from bookforge.camera_language.constants import SHOT_ANGLE_CLASS, SHOT_DISTANCE_CLASS, SHOT_PRIORITY_BY_FUNCTION
from bookforge.camera_language.types import ShotPlanEntry, ShotSequencePlan, ShotType, to_primitive


def _function(page: Dict[str, Any]) -> str:
    return str(page.get("narrative_function", "rising_action")).lower()


def _subject_focus(page: Dict[str, Any]) -> str:
    text = str(page.get("text", "")).lower()
    if "mara" in text and "patch" in text:
        return "mara and patch together"
    if "mara" in text:
        return "mara"
    if "patch" in text:
        return "patch"
    return "primary scene action"


def _choose_shot(function: str, prev: ShotType | None, recent: List[ShotType], idx: int, total: int) -> ShotType:
    priorities = SHOT_PRIORITY_BY_FUNCTION.get(function, SHOT_PRIORITY_BY_FUNCTION["rising_action"])
    pool = list(ShotType)

    if idx == 0:
        return ShotType.ESTABLISHING_WIDE
    if idx == total - 1:
        for candidate in [ShotType.ESTABLISHING_WIDE, ShotType.MEDIUM_INTERACTION, ShotType.CLOSEUP_EMOTION]:
            if candidate != prev:
                return candidate

    candidates = priorities + [shot for shot in pool if shot not in priorities]
    for shot in candidates:
        if prev and shot == prev:
            continue
        if function in {"climax", "reveal"} and shot in recent:
            continue
        if prev and SHOT_DISTANCE_CLASS.get(prev) == SHOT_DISTANCE_CLASS.get(shot) and SHOT_DISTANCE_CLASS.get(shot) in {"wide", "close"}:
            continue
        return shot

    return ShotType.MEDIUM_INTERACTION if prev != ShotType.MEDIUM_INTERACTION else ShotType.OVER_SHOULDER


def plan_camera_sequence(pages: List[Dict[str, Any]]) -> ShotSequencePlan:
    entries: List[ShotPlanEntry] = []
    recent: List[ShotType] = []

    for idx, page in enumerate(pages):
        page_no = int(page.get("page_number", idx + 1))
        function = _function(page)
        prev = entries[-1].shot_type if entries else None
        shot = _choose_shot(function, prev, recent[-3:], idx, len(pages))
        notes: List[str] = []
        if idx == 0 and shot != ShotType.ESTABLISHING_WIDE:
            notes.append("opening fallback could not use establishing_wide")
        if function in {"climax", "reveal"} and shot in recent[-3:]:
            notes.append("climax/reveal reused recent shot due to bounded constraints")

        entries.append(
            ShotPlanEntry(
                page_number=page_no,
                spread_number=int(page.get("spread_number", 0) or 0) or None,
                shot_type=shot,
                narrative_reason=f"{function} beat favors {shot.value} for progression.",
                target_distance_class=SHOT_DISTANCE_CLASS[shot],
                target_angle_class=SHOT_ANGLE_CLASS[shot],
                target_subject_focus=_subject_focus(page),
                sequence_priority=round(max(0.1, 1.0 - (idx / max(1, len(pages)))), 3),
                confidence=0.75,
                planning_notes=notes,
            )
        )
        recent.append(shot)

    diversity = len(set(e.shot_type for e in entries)) / max(1, len(ShotType))
    sequence_notes = [
        "Bounded camera planning generated per-page shot assignments.",
        "Adjacency guard prevents same shot type on neighboring pages.",
    ]
    return ShotSequencePlan(pages=entries, sequence_notes=sequence_notes, diversity_score=round(diversity, 4))


def write_planning_artifact(base_dir: Path, plan: ShotSequencePlan) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "pages": [to_primitive(p) for p in plan.pages],
        "sequence_notes": plan.sequence_notes,
        "diversity_score": plan.diversity_score,
    }
    (base_dir / "camera_sequence_plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
