from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def render_editorial_report_md(
    out_path: Path,
    dual_address: Dict[str, Any],
    rhythm: Dict[str, Any],
    hook_pack: Dict[str, Any],
    page_turn_map: List[Dict[str, Any]],
    artifact_summary: Dict[str, Any],
    eye_flow_warnings: List[Dict[str, Any]],
    readaloud_script_path: Path,
    trade_dress: Dict[str, Any],
) -> Path:
    lines = [
        "# Editorial / Commercial Analysis Report",
        "",
        "## Dual Address",
        f"- Child engagement signals: {len(dual_address.get('child_engagement_signals', []))}",
        f"- Adult gatekeeper signals: {len(dual_address.get('adult_gatekeeper_signals', []))}",
        f"- Read-aloud fatigue risk: {dual_address.get('read_aloud_fatigue_risk', {}).get('score', 'n/a')}",
        "",
        "## Rhythm Audit",
        f"- Smoothness score: {rhythm.get('read_aloud_smoothness_score', 'n/a')}",
        f"- Flagged lines: {len(rhythm.get('flagged_lines', []))}",
        "",
        "## Hook Pack",
        f"- Premise: {hook_pack.get('one_sentence_premise', '')}",
        f"- 15-second pitch: {hook_pack.get('15_second_pitch', '')}",
        "",
        "## Page-Turn Highlights",
    ]
    for row in page_turn_map[:6]:
        lines.append(f"- p{row.get('page_number')}: {row.get('recto_hook')} -> {row.get('verso_payoff')}")
    lines.extend([
        "",
        "## Hidden Artifacts Plan",
        f"- Selected plan: {artifact_summary.get('selected_plan_id', 'unselected')}",
        f"- Artifact types used: {', '.join(artifact_summary.get('artifact_types_used', []))}",
        "",
        "## Eye-Flow Warnings",
    ])
    if eye_flow_warnings:
        for warning in eye_flow_warnings:
            lines.append(f"- {warning.get('message')} ({warning.get('suggestion')})")
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Read-Aloud Script",
        f"- {readaloud_script_path.name}",
        "",
        "## Trade Dress Summary",
        f"- Typography: {trade_dress.get('title_typography_rule', '')}",
        f"- Badge location: {trade_dress.get('recurring_badge_icon_location', '')}",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
