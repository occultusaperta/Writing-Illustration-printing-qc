from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List

from bookforge.character_scoring.types import CharacterCommercialReport, CharacterSequenceFinding


def _safe_page_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _find_best_by_page(qa_attempts: List[Dict[str, Any]], page_count: int) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        p = _safe_page_int(row.get("page"))
        if 1 <= p <= page_count and isinstance(row.get("best"), dict):
            out[p] = row["best"]
    return out


def build_character_commercial_report(*, page_count: int, qa_attempts: List[Dict[str, Any]] | None, enabled: bool = True) -> CharacterCommercialReport:
    limitations = [
        "Uses bounded visual heuristics only; no biometric certainty is claimed.",
        "Scores are additive QA/review signals, not hard commercial outcome predictions.",
    ]
    if not enabled:
        return CharacterCommercialReport(
            enabled=False,
            summary_score=0.0,
            lead_character_strength_summary="Disabled by feature flag.",
            strongest_pages=[],
            weakest_pages=[],
            consistency_notes=["Character commercial scoring disabled."],
            warnings=[],
            positive_notes=[],
            limitations=limitations,
        )

    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []
    by_page = _find_best_by_page(qa_attempts, page_count)

    findings: List[CharacterSequenceFinding] = []
    for page in range(1, page_count + 1):
        best = by_page.get(page, {})
        metadata = best.get("metadata", {}) if isinstance(best.get("metadata"), dict) else {}
        ccs = metadata.get("character_commercial_score") if isinstance(metadata.get("character_commercial_score"), dict) else {}
        baby = metadata.get("baby_schema_score") if isinstance(metadata.get("baby_schema_score"), dict) else {}
        toy = metadata.get("toyetic_score") if isinstance(metadata.get("toyetic_score"), dict) else {}
        sil = metadata.get("silhouette_score") if isinstance(metadata.get("silhouette_score"), dict) else {}

        if not ccs:
            continue
        findings.append(
            CharacterSequenceFinding(
                page=page,
                composite_score=float(ccs.get("composite_score", 0.0) or 0.0),
                baby_schema_score=float(baby.get("composite_score", 0.0) or 0.0),
                toyetic_score=float(toy.get("composite_score", 0.0) or 0.0),
                silhouette_score=float(sil.get("composite_score", 0.0) or 0.0),
                confidence=float(ccs.get("confidence", 0.0) or 0.0),
                notes=list(ccs.get("notes", []) or []),
                warnings=list(ccs.get("warnings", []) or []),
            )
        )

    if not findings:
        return CharacterCommercialReport(
            enabled=True,
            summary_score=0.0,
            lead_character_strength_summary="Insufficient character metadata for commercial scoring.",
            strongest_pages=[],
            weakest_pages=[],
            consistency_notes=[],
            warnings=["No page-level character commercial metadata was available."],
            positive_notes=[],
            limitations=limitations,
        )

    ranked = sorted(findings, key=lambda f: f.composite_score, reverse=True)
    strongest = ranked[: min(3, len(ranked))]
    weakest = sorted(findings, key=lambda f: f.composite_score)[: min(3, len(ranked))]

    score_series = [f.composite_score for f in findings]
    summary_score = float(mean(score_series))
    spread = max(score_series) - min(score_series)

    consistency_notes: List[str] = []
    warnings: List[str] = []
    positive_notes: List[str] = []

    if spread > 0.35:
        warnings.append("Character identity/commercial strength varies significantly across pages.")
    else:
        consistency_notes.append("Character commercial profile appears reasonably consistent across the sequence.")

    if summary_score < 0.45:
        warnings.append("Lead character commercial potential is weak in current selected pages.")
    elif summary_score > 0.72:
        positive_notes.append("Lead character demonstrates strong repeatable commercial identity.")

    if any(f.baby_schema_score < 0.4 for f in findings):
        warnings.append("Some pages show low baby-schema cuteness proxies.")
    if any(f.toyetic_score < 0.4 for f in findings):
        warnings.append("Some pages show low toyetic/signature-feature strength.")
    if any(f.silhouette_score < 0.35 for f in findings):
        warnings.append("Some pages show weak silhouette readability for small-scale recognition.")

    summary = "Strong" if summary_score >= 0.7 else "Moderate" if summary_score >= 0.5 else "Weak"

    return CharacterCommercialReport(
        enabled=True,
        summary_score=round(summary_score, 4),
        lead_character_strength_summary=f"{summary} lead-character commercial profile based on additive proxy signals.",
        strongest_pages=strongest,
        weakest_pages=weakest,
        consistency_notes=consistency_notes,
        warnings=warnings,
        positive_notes=positive_notes,
        limitations=limitations,
    )
