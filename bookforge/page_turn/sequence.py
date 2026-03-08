from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from bookforge.io import write_json
from bookforge.page_turn.types import PageTurnSequenceFinding, PageTurnTensionReport


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


def _runs(values: List[int]) -> List[List[int]]:
    if not values:
        return []
    values = sorted(set(values))
    runs: List[List[int]] = []
    cur = [values[0]]
    for p in values[1:]:
        if p == cur[-1] + 1:
            cur.append(p)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [p]
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def build_page_turn_tension_report(*, page_count: int, qa_attempts: List[Dict[str, Any]] | None, enabled: bool = True) -> PageTurnTensionReport:
    limitations = [
        "Heuristic proxy analysis only; it does not provide true motion, gaze, or narrative certainty.",
        "Uses bounded local metadata and image-derived cues without open-ended regeneration.",
    ]
    if not enabled:
        return PageTurnTensionReport(
            enabled=False,
            summary_score=0.0,
            weak_turn_runs=[],
            leftward_resistance_runs=[],
            over_resolved_turns=[],
            flat_page_turn_rhythm_clusters=[],
            strong_turn_pages=[],
            climax_reveal_turn_support_pages=[],
            warnings=[],
            positive_notes=["Page-turn tension layer disabled by feature flag."],
            limitations=limitations,
            findings=[],
        )

    qa_attempts = qa_attempts if isinstance(qa_attempts, list) else []
    by_page = _best_by_page(qa_attempts, page_count)
    findings: List[PageTurnSequenceFinding] = []
    for page in range(1, page_count + 1):
        best = by_page.get(page, {})
        meta = best.get("metadata", {}) if isinstance(best.get("metadata", {}), dict) else {}
        turn = meta.get("page_turn_tension_score", {}) if isinstance(meta.get("page_turn_tension_score", {}), dict) else {}
        if not turn:
            continue
        findings.append(
            PageTurnSequenceFinding(
                page=page,
                page_turn_tension_score=round(float(turn.get("page_turn_tension_score", 0.0) or 0.0), 4),
                turn_resistance_penalty=round(float(turn.get("turn_resistance_penalty", 0.0) or 0.0), 4),
                confidence=round(float(turn.get("confidence", 0.0) or 0.0), 4),
                notes=list(turn.get("notes", []) or [])[:4],
                warnings=list(turn.get("warnings", []) or [])[:4],
            )
        )

    if not findings:
        return PageTurnTensionReport(
            enabled=True,
            summary_score=0.0,
            weak_turn_runs=[],
            leftward_resistance_runs=[],
            over_resolved_turns=[],
            flat_page_turn_rhythm_clusters=[],
            strong_turn_pages=[],
            climax_reveal_turn_support_pages=[],
            warnings=["No page_turn_tension_score metadata found in QA attempts."],
            positive_notes=[],
            limitations=limitations,
            findings=[],
        )

    weak_pages = [f.page for f in findings if f.page_turn_tension_score < 0.43]
    left_resist_pages = [f.page for f in findings if f.turn_resistance_penalty > 0.58]
    over_resolved_turns = [f.page for f in findings if f.page_turn_tension_score < 0.4 and f.turn_resistance_penalty > 0.62]
    strong_turn_pages = [f.page for f in findings if f.page_turn_tension_score >= 0.72 and f.turn_resistance_penalty <= 0.45]

    rhythm_flat_pages = []
    for i in range(1, len(findings)):
        if abs(findings[i].page_turn_tension_score - findings[i - 1].page_turn_tension_score) < 0.04:
            rhythm_flat_pages.extend([findings[i - 1].page, findings[i].page])

    climax_start = max(1, page_count - 2)
    climax_support = [f.page for f in findings if f.page >= climax_start and f.page_turn_tension_score >= 0.6]

    warnings: List[str] = []
    positive_notes: List[str] = []
    if weak_pages:
        warnings.append("Detected weak page-turn momentum run(s) in right-page flow proxies.")
    if left_resist_pages:
        warnings.append("Detected leftward resistance / closure-heavy run(s).")
    if len(strong_turn_pages) >= 2:
        positive_notes.append("Multiple pages show strong forward page-turn momentum proxies.")
    if climax_support:
        positive_notes.append("Climax/reveal-zone pages retain turn support proxies.")

    if page_count >= 1 and findings[-1].page == page_count and findings[-1].page_turn_tension_score < 0.4:
        positive_notes.append("Ending page calm-down detected; over-penalization is intentionally avoided.")

    summary_score = round(float(mean([f.page_turn_tension_score for f in findings])), 4)

    return PageTurnTensionReport(
        enabled=True,
        summary_score=summary_score,
        weak_turn_runs=_runs(weak_pages),
        leftward_resistance_runs=_runs(left_resist_pages),
        over_resolved_turns=over_resolved_turns,
        flat_page_turn_rhythm_clusters=_runs(rhythm_flat_pages),
        strong_turn_pages=strong_turn_pages,
        climax_reveal_turn_support_pages=climax_support,
        warnings=warnings,
        positive_notes=positive_notes,
        limitations=limitations,
        findings=findings,
    )


def write_page_turn_tension_report(path: Path, report: PageTurnTensionReport) -> None:
    write_json(path, report.to_dict())
