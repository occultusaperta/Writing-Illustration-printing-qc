from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from bookforge.hidden_world.types import (
    HiddenDetailPlan,
    HiddenDetailType,
    HiddenWorldSequencePlan,
    PageHiddenWorldPlan,
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:64] or "detail"


def _extract_note_hints(note: str) -> Dict[str, List[str]]:
    n = note.strip()
    if not n:
        return {"foreshadow": [], "callback": [], "parent": [], "motifs": []}
    buckets = {"foreshadow": [], "callback": [], "parent": [], "motifs": []}
    lines = [x.strip(" -•\t") for x in re.split(r"[\n;]", n) if x.strip()]
    for ln in lines:
        low = ln.lower()
        if any(k in low for k in ["foreshadow", "hint", "early echo"]):
            buckets["foreshadow"].append(ln)
        if any(k in low for k in ["callback", "echo", "repeat later", "again"]):
            buckets["callback"].append(ln)
        if any(k in low for k in ["parent", "adult", "background story", "woodgrain", "wall", "fabric", "pattern"]):
            buckets["parent"].append(ln)
        if any(k in low for k in ["motif", "recurring", "tiny", "hidden", "find me"]):
            buckets["motifs"].append(ln)
    return buckets


def plan_hidden_world_sequence(
    *,
    pages: List[Dict[str, Any]],
    architecture_by_page: Dict[int, Dict[str, Any]] | None = None,
    camera_by_page: Dict[int, Dict[str, Any]] | None = None,
    saliency_by_page: Dict[int, Dict[str, Any]] | None = None,
) -> HiddenWorldSequencePlan:
    architecture_by_page = architecture_by_page or {}
    camera_by_page = camera_by_page or {}
    saliency_by_page = saliency_by_page or {}

    detail_plans: List[HiddenDetailPlan] = []
    page_plans: List[PageHiddenWorldPlan] = []
    recurring_motifs: Dict[str, set[int]] = {}
    warnings: List[str] = []
    notes: List[str] = [
        "Hidden world planning is deterministic and metadata-first.",
        "Manuscript-required hidden details are highest priority.",
    ]

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_no = int(page.get("page_number", 0) or 0)
        if page_no <= 0:
            continue
        required = [str(x).strip() for x in page.get("required_hidden_details", []) if str(x).strip()]
        note_text = str(page.get("illustration_notes", "")).strip()
        buckets = _extract_note_hints(note_text)

        recurring = [x for x in buckets["motifs"] if x not in required]
        if required:
            recurring.extend([x for x in required if len(x.split()) <= 8])
        recurring = sorted(set(recurring))

        foreshadow = buckets["foreshadow"]
        callback = buckets["callback"]
        parent_reward = buckets["parent"]

        visibility_targets: Dict[str, str] = {}
        for d in required:
            visibility_targets[d] = "moderate"
        for d in recurring:
            visibility_targets.setdefault(d, "subtle")
        for d in foreshadow + callback + parent_reward:
            visibility_targets.setdefault(d, "subtle")

        for d in required:
            detail_plans.append(
                HiddenDetailPlan(
                    detail_id=f"required-{page_no}-{_slug(d)}",
                    detail_text=d,
                    detail_type=HiddenDetailType.REQUIRED,
                    source="manuscript.required_hidden_details",
                    page_numbers=[page_no],
                    visibility_target=visibility_targets[d],
                    recurrence_expected=1,
                )
            )

        for text in recurring:
            recurring_motifs.setdefault(text, set()).add(page_no)

        arch = architecture_by_page.get(page_no, {})
        arch_text_zone = bool((arch.get("text_zone") or arch.get("zones")))
        cam = camera_by_page.get(page_no, {})
        shot_type = str(cam.get("shot_type", ""))
        saliency = saliency_by_page.get(page_no, {})
        notes_page: List[str] = []
        if arch_text_zone:
            notes_page.append("avoid_text_zone_collision")
        if shot_type in {"closeup_emotion", "hero_closeup"}:
            notes_page.append("subtle_details_keep_secondary_to_focal_action")
        if saliency:
            notes_page.append("prefer_subtle_hidden_details_outside_peak_saliency")

        page_plans.append(
            PageHiddenWorldPlan(
                page_number=page_no,
                required_details=required,
                recurring_motifs=recurring,
                foreshadowing_hints=foreshadow,
                callback_hints=callback,
                parent_reward_details=parent_reward,
                visibility_targets=visibility_targets,
                discoverable_not_dominant=True,
                notes=notes_page,
            )
        )

    for motif, pages_set in recurring_motifs.items():
        ordered = sorted(pages_set)
        detail_plans.append(
            HiddenDetailPlan(
                detail_id=f"motif-{_slug(motif)}",
                detail_text=motif,
                detail_type=HiddenDetailType.RECURRING_MOTIF,
                source="illustration_notes+required_hidden_details",
                page_numbers=ordered,
                visibility_target="subtle",
                recurrence_expected=max(2, min(4, len(ordered))),
            )
        )
        if len(ordered) < 2:
            warnings.append(f"Recurring motif '{motif}' currently appears on only one page.")

    page_numbers = sorted([p.page_number for p in page_plans])
    if page_numbers and len(page_numbers) >= 4:
        for i in range(1, len(page_numbers)):
            if page_numbers[i] - page_numbers[i - 1] > 4:
                warnings.append(f"Weak hidden-detail continuity gap between pages {page_numbers[i - 1]} and {page_numbers[i]}.")

    return HiddenWorldSequencePlan(
        page_count=len(page_plans),
        recurring_motifs=sorted(recurring_motifs.keys()),
        detail_plans=detail_plans,
        pages=sorted(page_plans, key=lambda x: x.page_number),
        warnings=warnings,
        notes=notes,
    )


def write_hidden_world_plan(path: Path, plan: HiddenWorldSequencePlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
