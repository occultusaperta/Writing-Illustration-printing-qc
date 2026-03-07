from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from bookforge.dual_audience.types import DualAudienceReport, DualAudienceSequenceFinding


def _safe_page_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _best_by_page(qa_attempts: List[Dict[str, Any]], page_count: int) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        page = _safe_page_int(row.get("page"))
        if 1 <= page <= page_count and isinstance(row.get("best"), dict):
            out[page] = row["best"]
    return out


def build_dual_audience_report(*, page_count: int, qa_attempts: List[Dict[str, Any]] | None, enabled: bool = True) -> DualAudienceReport:
    limitations = [
        "Heuristic proxy layer only; no direct child-user or caregiver preference testing is performed.",
        "Designed as additive QA/review support, not a dominant ranking rewrite.",
    ]
    if not enabled:
        return DualAudienceReport(
            enabled=False,
            summary_score=0.0,
            child_channel_summary_score=0.0,
            adult_channel_summary_score=0.0,
            balance_summary_score=0.0,
            strongest_pages=[],
            weakest_pages=[],
            child_confusion_risk_pages=[],
            adult_flatness_risk_pages=[],
            imbalance_pages=[],
            positive_notes=["Dual-audience layer disabled by feature flag."],
            warnings=[],
            limitations=limitations,
        )

    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []
    by_page = _best_by_page(qa_attempts, page_count)
    findings: List[DualAudienceSequenceFinding] = []
    for page in range(1, page_count + 1):
        best = by_page.get(page, {})
        meta = best.get("metadata", {}) if isinstance(best.get("metadata", {}), dict) else {}
        dual = meta.get("dual_audience_score", {}) if isinstance(meta.get("dual_audience_score", {}), dict) else {}
        if not dual:
            continue
        child = float(((dual.get("child_channel_score") or {}).get("composite_score", 0.0)) or 0.0)
        adult = float(((dual.get("adult_channel_score") or {}).get("composite_score", 0.0)) or 0.0)
        findings.append(
            DualAudienceSequenceFinding(
                page=page,
                child_channel_score=round(child, 4),
                adult_channel_score=round(adult, 4),
                balance_score=round(float(dual.get("balance_score", 0.0) or 0.0), 4),
                composite_score=round(float(dual.get("composite_score", 0.0) or 0.0), 4),
                confidence=round(float(dual.get("confidence", 0.0) or 0.0), 4),
                notes=list(dual.get("notes", []) or [])[:5],
                warnings=list(dual.get("warnings", []) or [])[:5],
            )
        )

    if not findings:
        return DualAudienceReport(
            enabled=True,
            summary_score=0.0,
            child_channel_summary_score=0.0,
            adult_channel_summary_score=0.0,
            balance_summary_score=0.0,
            strongest_pages=[],
            weakest_pages=[],
            child_confusion_risk_pages=[],
            adult_flatness_risk_pages=[],
            imbalance_pages=[],
            positive_notes=[],
            warnings=["No dual-audience metadata found in QA attempts."],
            limitations=limitations,
        )

    child_confusion = [f.page for f in findings if f.child_channel_score < 0.45]
    adult_flat = [f.page for f in findings if f.adult_channel_score < 0.45]
    imbalance = [f.page for f in findings if f.balance_score < 0.55]
    strongest = sorted(findings, key=lambda x: x.composite_score, reverse=True)[: min(3, len(findings))]
    weakest = sorted(findings, key=lambda x: x.composite_score)[: min(3, len(findings))]

    child_mean = float(mean([f.child_channel_score for f in findings]))
    adult_mean = float(mean([f.adult_channel_score for f in findings]))
    bal_mean = float(mean([f.balance_score for f in findings]))
    summary = float(mean([f.composite_score for f in findings]))

    positive_notes: List[str] = []
    warnings: List[str] = []
    if summary >= 0.7:
        positive_notes.append("Dual-audience layer indicates strong cross-audience page quality on average.")
    if child_confusion:
        warnings.append("Some pages have elevated child-channel confusion risk proxies.")
    if adult_flat:
        warnings.append("Some pages have elevated adult-channel flatness risk proxies.")
    if imbalance:
        warnings.append("Some pages are materially imbalanced between child and adult channels.")

    return DualAudienceReport(
        enabled=True,
        summary_score=round(summary, 4),
        child_channel_summary_score=round(child_mean, 4),
        adult_channel_summary_score=round(adult_mean, 4),
        balance_summary_score=round(bal_mean, 4),
        strongest_pages=strongest,
        weakest_pages=weakest,
        child_confusion_risk_pages=child_confusion,
        adult_flatness_risk_pages=adult_flat,
        imbalance_pages=imbalance,
        positive_notes=positive_notes,
        warnings=warnings,
        limitations=limitations,
    )


def write_dual_audience_report(path: Path, report: DualAudienceReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
