from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from bookforge.sequence_optimizer.search import accepted_move_paths
from bookforge.sequence_optimizer.types import SequenceOptimizationReport


def write_sequence_optimization_report(path: Path, report: SequenceOptimizationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def apply_sequence_optimization_decisions(
    *,
    selected: List[str],
    qa_attempts: List[Dict[str, Any]],
    report: SequenceOptimizationReport,
) -> SequenceOptimizationReport:
    if not report.enabled or not report.accepted_moves:
        return report

    latest_by_page: Dict[int, Dict[str, Any]] = {}
    for row in qa_attempts:
        page = row.get("page")
        if not isinstance(page, int):
            continue
        prev = latest_by_page.get(page)
        if prev is None or int(row.get("attempt", 0) or 0) >= int(prev.get("attempt", 0) or 0):
            latest_by_page[page] = row

    for page, candidate_path in accepted_move_paths(report):
        if not (0 < page <= len(selected)):
            continue
        page_path = Path(selected[page - 1])
        alt = Path(candidate_path)
        if not page_path.exists() or not alt.exists():
            continue
        with Image.open(page_path) as base_im, Image.open(alt) as cand_im:
            base = base_im.convert("RGB")
            cand = cand_im.convert("RGB")
            if cand.size != base.size:
                cand = cand.resize(base.size, Image.Resampling.LANCZOS)
            cand.save(page_path, "PNG")

        latest = latest_by_page.get(page)
        if latest and isinstance(latest.get("variants", []), list):
            match = next((v for v in latest.get("variants", []) if isinstance(v, dict) and str(v.get("path", "")) == str(alt)), None)
            if isinstance(match, dict):
                latest["best"] = dict(match)

    return report
