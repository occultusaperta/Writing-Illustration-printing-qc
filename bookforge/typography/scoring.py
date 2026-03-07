from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List

from bookforge.typography.types import PageTypographyPlan, TypographyScoreResult, TypographySequenceFinding


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def score_typography_plan(
    plan: PageTypographyPlan,
    *,
    saliency_context: Dict[str, Any] | None = None,
    page_architecture_context: Dict[str, Any] | None = None,
) -> TypographyScoreResult:
    saliency_context = saliency_context if isinstance(saliency_context, dict) else {}
    arch = page_architecture_context if isinstance(page_architecture_context, dict) else {}

    contrast_hint = float((saliency_context.get("text_zone_quietness_score", {}) or {}).get("quietness_score", 0.6) or 0.6)
    contrast_readability_score = _clamp01(0.55 + 0.45 * contrast_hint)

    text_zone = plan.text_zone
    zone_area = text_zone["w"] * text_zone["h"]
    text_zone_quietness_score = _clamp01(0.9 - max(0.0, 0.2 - zone_area))

    line_count = max(1, len([ln for ln in plan.lines if ln.line_text.strip()]))
    fit_score = _clamp01(1.0 - max(0.0, (line_count - 7) * 0.08))

    expressive_roles = [ln.role for ln in plan.lines if ln.role != "body"]
    expressive_alignment_score = _clamp01(0.95 - abs(len(expressive_roles) - 2) * 0.1)

    rhythm_penalty = sum(0.12 for ln in plan.lines if ln.line_gap_multiplier > 1.3)
    readaloud_rhythm_score = _clamp01(0.92 - rhythm_penalty)

    print_safety_score = _clamp01(0.95 if zone_area >= 0.08 else 0.72)
    if bool(arch.get("gutter_sensitive", False)) and text_zone["x"] < 0.1:
        print_safety_score = _clamp01(print_safety_score - 0.1)

    warnings: List[str] = []
    notes: List[str] = []
    if fit_score < 0.6:
        warnings.append("Typography fit risk: too many lines for the planned zone.")
    if contrast_readability_score < 0.65:
        warnings.append("Typography contrast may be weak in current text zone.")
    if expressive_alignment_score < 0.5:
        warnings.append("Expressive typography may overreach page tone.")
    if plan.special_positioning_mode != "anchored":
        notes.append("Special positioning mode active.")

    composite = _clamp01(
        0.2 * contrast_readability_score
        + 0.18 * text_zone_quietness_score
        + 0.2 * fit_score
        + 0.16 * expressive_alignment_score
        + 0.14 * readaloud_rhythm_score
        + 0.12 * print_safety_score
    )

    return TypographyScoreResult(
        contrast_readability_score=round(contrast_readability_score, 4),
        text_zone_quietness_score=round(text_zone_quietness_score, 4),
        fit_score=round(fit_score, 4),
        expressive_alignment_score=round(expressive_alignment_score, 4),
        readaloud_rhythm_score=round(readaloud_rhythm_score, 4),
        print_safety_score=round(print_safety_score, 4),
        composite_score=round(composite, 4),
        confidence=0.82,
        warnings=warnings,
        notes=notes,
    )


def build_typography_sequence_finding(page_rows: List[Dict[str, Any]]) -> TypographySequenceFinding:
    scores = [float((row.get("typography_score", {}) or {}).get("composite_score", 0.0) or 0.0) for row in page_rows]
    high_quality = [int(row.get("page", 0)) for row in page_rows if float((row.get("typography_score", {}) or {}).get("composite_score", 0.0) or 0.0) >= 0.82]
    crowding = [int(row.get("page", 0)) for row in page_rows if float((row.get("typography_score", {}) or {}).get("fit_score", 1.0) or 1.0) < 0.62]
    weak_contrast = [int(row.get("page", 0)) for row in page_rows if float((row.get("typography_score", {}) or {}).get("contrast_readability_score", 1.0) or 1.0) < 0.64]
    overreach = [int(row.get("page", 0)) for row in page_rows if float((row.get("typography_score", {}) or {}).get("expressive_alignment_score", 1.0) or 1.0) < 0.5]
    reveal_success = [int(row.get("page", 0)) for row in page_rows if "title_dramatic" in (row.get("style_roles", []) or []) and float((row.get("typography_score", {}) or {}).get("composite_score", 0.0) or 0.0) >= 0.75]
    fallback = [int(row.get("page", 0)) for row in page_rows if bool(row.get("render_fallback", False))]

    notes: List[str] = []
    if high_quality:
        notes.append("Strong typography readability and expression on select pages.")
    if crowding:
        notes.append("Some pages are crowding-prone; consider reducing line density upstream.")
    if not notes:
        notes.append("Typography diagnostics completed with bounded rule-based checks.")

    return TypographySequenceFinding(
        summary_score=round(_clamp01(mean(scores) if scores else 0.0), 4),
        high_quality_pages=high_quality,
        crowding_risk_pages=crowding,
        weak_contrast_pages=weak_contrast,
        overreach_pages=overreach,
        reveal_success_pages=reveal_success,
        fallback_pages=fallback,
        sequence_notes=notes,
    )
