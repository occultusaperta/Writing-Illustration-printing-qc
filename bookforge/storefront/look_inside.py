from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.storefront.types import LookInsidePageScore, LookInsideSequenceReport, StorefrontSequenceFinding


def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _image_focal_strength(path: Path) -> float:
    with Image.open(path) as im:
        arr = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = arr.shape
    c = arr[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]
    if c.size == 0:
        return 0.5
    return _clip01(0.35 + float(np.std(c)) / 95.0)


def _hook_score(path: Path) -> float:
    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    sat = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    contrast = float(np.std(np.mean(rgb, axis=2)))
    return _clip01(0.22 + float(np.mean(sat)) / 140.0 + contrast / 90.0)


def _priority_pages(page_count: int) -> List[int]:
    window = min(page_count, 8)
    return list(range(1, window + 1))


def build_look_inside_sequence_report(
    *,
    selected: List[str],
    qa_attempts: List[Dict[str, Any]],
    color_script: Dict[str, Any] | None,
    architecture_plan: List[Dict[str, Any]] | None,
    camera_sequence_plan: Dict[int, Dict[str, Any]] | None,
    hidden_world_plan: Dict[str, Any] | None,
) -> LookInsideSequenceReport:
    page_count = len(selected)
    priorities = _priority_pages(page_count)
    qa_by_page: Dict[int, Dict[str, Any]] = {int(a.get("page", 0)): a.get("best", {}) for a in qa_attempts if isinstance(a, dict)}
    arch_by_page: Dict[int, Dict[str, Any]] = {int(a.get("page_number", 0)): a for a in (architecture_plan or []) if isinstance(a, dict)}

    color_pages = {int(p.get("page_number", 0)): p for p in ((color_script or {}).get("pages", []) if isinstance(color_script, dict) else []) if isinstance(p, dict)}
    hidden_pages = {int(p.get("page_number", 0)): p for p in ((hidden_world_plan or {}).get("pages", []) if isinstance(hidden_world_plan, dict) else []) if isinstance(p, dict)}

    page_scores: List[LookInsidePageScore] = []
    warnings: List[str] = []
    positives: List[str] = []
    findings: List[StorefrontSequenceFinding] = []

    for p in priorities:
        idx = p - 1
        if idx >= len(selected):
            continue
        path = Path(selected[idx])
        best = qa_by_page.get(p, {}) if isinstance(qa_by_page.get(p, {}), dict) else {}
        meta = best.get("metadata", {}) if isinstance(best.get("metadata", {}), dict) else {}

        focal_strength = _image_focal_strength(path)
        saliency = float(((meta.get("saliency_flow_score") or {}).get("composite_score", 0.5) or 0.5))
        typography = float(((meta.get("typography_score") or {}).get("composite_score", 0.72) or 0.72))
        emotional_hook = _hook_score(path)
        color_strength = float(((meta.get("color_score") or {}).get("composite_score", 0.6) or 0.6))
        hidden_delight = float(((meta.get("hidden_world_score") or {}).get("composite_score", 0.5) or 0.5))

        arch_score = float(((meta.get("page_architecture_score") or {}).get("composite_score", 0.62) or 0.62))
        if p in arch_by_page and p in (camera_sequence_plan or {}):
            arch_score = _clip01(arch_score + 0.05)

        page_warnings: List[str] = []
        page_notes: List[str] = []

        if p == 1 and emotional_hook < 0.45:
            page_warnings.append("opening_hook_weak")
        if typography < 0.45:
            page_warnings.append("typography_readability_weak")
        if saliency < 0.42:
            page_warnings.append("saliency_flow_weak")
        if focal_strength < 0.42:
            page_warnings.append("focal_strength_weak")
        if float(best.get("text_likelihood", 0.0) or 0.0) > 0.16:
            page_warnings.append("text_heavy_preview_risk")
        if float(best.get("contrast", 0.0) or 0.0) < 20.0:
            page_warnings.append("low_contrast_preview_risk")

        if p in color_pages:
            page_notes.append("color_script_planning_available")
        if p in hidden_pages:
            page_notes.append("hidden_world_detail_planned")

        composite = _clip01(
            0.2 * focal_strength
            + 0.17 * saliency
            + 0.13 * typography
            + 0.18 * emotional_hook
            + 0.12 * color_strength
            + 0.08 * hidden_delight
            + 0.12 * arch_score
        )

        row = LookInsidePageScore(
            page_number=p,
            image_path=str(path),
            focal_strength_score=round(focal_strength, 4),
            saliency_flow_score=round(saliency, 4),
            typography_readability_score=round(typography, 4),
            emotional_hook_score=round(emotional_hook, 4),
            color_script_strength_score=round(color_strength, 4),
            hidden_world_delight_score=round(hidden_delight, 4),
            architecture_camera_strength_score=round(arch_score, 4),
            composite_score=round(composite, 4),
            warnings=page_warnings,
            notes=page_notes,
        )
        page_scores.append(row)

    if page_scores:
        strong = max(page_scores, key=lambda x: x.composite_score)
        weak = min(page_scores, key=lambda x: x.composite_score)
    else:
        strong = None
        weak = None

    for row in page_scores:
        if row.composite_score < 0.47:
            warnings.append(f"weak_preview_page:{row.page_number}")
            findings.append(StorefrontSequenceFinding("look_inside", "warning", row.page_number, "Preview page appears weak for storefront conversion."))
        if row.composite_score > 0.72:
            positives.append(f"Page {row.page_number} is likely a strong Look Inside preview anchor.")

    if page_scores and np.mean([p.composite_score for p in page_scores[:3]]) < 0.52:
        warnings.append("opening_preview_window_underpowered")
        findings.append(StorefrontSequenceFinding("look_inside", "warning", None, "Opening preview window lacks strong conversion hooks."))

    return LookInsideSequenceReport(
        priority_pages=priorities,
        page_scores=page_scores,
        strongest_page=(strong.page_number if strong else None),
        weakest_page=(weak.page_number if weak else None),
        preview_segment_score=round(float(np.mean([p.composite_score for p in page_scores])) if page_scores else 0.0, 4),
        positive_notes=positives[:6],
        warnings=warnings,
        findings=findings,
    )
