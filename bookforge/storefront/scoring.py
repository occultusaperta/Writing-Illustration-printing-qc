from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from bookforge.io import write_json
from bookforge.storefront.look_inside import build_look_inside_sequence_report
from bookforge.storefront.sequence import build_storefront_sequence_findings
from bookforge.storefront.thumbnail import score_cover_thumbnail
from bookforge.storefront.types import CoverThumbnailDiagnostics, LookInsideSequenceReport, StorefrontOptimizationReport


def build_storefront_optimization_report(
    *,
    selected: List[str],
    cover_path: str | None,
    qa_attempts: List[Dict[str, Any]],
    color_script: Dict[str, Any] | None,
    architecture_plan: List[Dict[str, Any]] | None,
    camera_sequence_plan: Dict[int, Dict[str, Any]] | None,
    hidden_world_plan: Dict[str, Any] | None,
    enabled: bool = True,
) -> StorefrontOptimizationReport:
    if not enabled:
        look = LookInsideSequenceReport(
            priority_pages=[],
            page_scores=[],
            strongest_page=None,
            weakest_page=None,
            preview_segment_score=0.0,
            positive_notes=[],
            warnings=[],
            findings=[],
        )
        return StorefrontOptimizationReport(
            enabled=False,
            cover_thumbnail=None,
            look_inside=look,
            first_pages_strength_score=0.0,
            summary_score=0.0,
            warnings=[],
            notes=["Storefront optimization disabled by feature flag."],
            limitations=["No storefront diagnostics generated because feature flag is disabled."],
        )

    cover_diag: CoverThumbnailDiagnostics | None = None
    warnings: List[str] = []
    notes: List[str] = []
    if cover_path and Path(cover_path).exists():
        cover_diag = score_cover_thumbnail(Path(cover_path), title_text_available=False)
    else:
        warnings.append("cover_thumbnail_unavailable")

    look = build_look_inside_sequence_report(
        selected=selected,
        qa_attempts=qa_attempts,
        color_script=color_script,
        architecture_plan=architecture_plan,
        camera_sequence_plan=camera_sequence_plan,
        hidden_world_plan=hidden_world_plan,
    )
    look.findings.extend(build_storefront_sequence_findings(look.page_scores))

    first_pages_strength = look.preview_segment_score
    cover_score = cover_diag.aggregate.composite_score if cover_diag else 0.0
    summary_score = round(min(1.0, 0.45 * cover_score + 0.55 * first_pages_strength), 4)

    if cover_diag and cover_diag.aggregate.title_readability_score < 0.43:
        warnings.append("title_readability_at_thumbnail_is_weak")
    if cover_diag and cover_diag.aggregate.clutter_penalty > 0.58:
        warnings.append("cover_clutter_risk_at_thumbnail")
    if look.preview_segment_score < 0.52:
        warnings.append("look_inside_preview_window_needs_strengthening")

    notes.extend(look.positive_notes)

    return StorefrontOptimizationReport(
        enabled=True,
        cover_thumbnail=cover_diag,
        look_inside=look,
        first_pages_strength_score=round(first_pages_strength, 4),
        summary_score=summary_score,
        warnings=warnings,
        notes=notes,
        limitations=[
            "Scoring is internal heuristic analysis and does not use live competitor cover data.",
            "No CTR/sales prediction is performed.",
            "Title readability is estimated from image proxies when rendered text layers/OCR are unavailable.",
        ],
    )


def write_storefront_optimization_report(path: Path, report: StorefrontOptimizationReport) -> None:
    write_json(path, report.to_dict())
