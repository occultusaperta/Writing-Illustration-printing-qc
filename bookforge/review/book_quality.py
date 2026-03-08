from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bookforge.io import write_json

SCHEMA_VERSION = "1.0"
MASTER_ARTIFACT_NAME = "book_quality_report.json"
LEGACY_ARTIFACTS = [
    "book_sequence_report.json",
    "layout_search_report.json",
    "typography_report.json",
    "reselection_report.json",
    "targeted_regeneration_report.json",
    "sequence_optimization_report.json",
    "hidden_world_report.json",
    "storefront_optimization_report.json",
    "character_commercial_report.json",
    "dual_audience_report.json",
    "page_turn_tension_report.json",
]


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _as_list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float))]


def build_book_quality_report(review_dir: Path) -> Dict[str, Any]:
    production_report = _read_json(review_dir / "production_report.json") or {}
    reports = {name: _read_json(review_dir / name) for name in LEGACY_ARTIFACTS}
    sequence = reports.get("book_sequence_report.json") or {}

    dual_enabled = bool((production_report.get("dual_audience") or {}).get("enabled", True))
    page_turn_enabled = bool((production_report.get("page_turn_tension") or {}).get("enabled", True))

    warnings: List[Dict[str, Any]] = []
    limitations: List[Dict[str, Any]] = []

    for artifact_name, payload in reports.items():
        if payload is None:
            warnings.append({"source": artifact_name, "message": f"Missing legacy artifact {artifact_name}."})
            continue
        for note in _as_list_of_strings(payload.get("warnings", [])):
            warnings.append({"source": artifact_name, "message": note})
        for note in _as_list_of_strings(payload.get("limitations", [])):
            limitations.append({"source": artifact_name, "message": note})

    if not dual_enabled:
        limitations.append({"source": "dual_audience", "message": "Dual-audience analysis disabled by feature flag."})
    if not page_turn_enabled:
        limitations.append({"source": "page_turn_tension", "message": "Page-turn tension analysis disabled by feature flag."})

    summary_scores = {
        "overall_sequence_score": float(sequence.get("overall_sequence_score", 0.0) or 0.0),
        "color_flow_summary_score": float(sequence.get("color_flow_summary_score", 0.0) or 0.0),
        "architecture_flow_summary_score": float(sequence.get("architecture_flow_summary_score", 0.0) or 0.0),
        "energy_curve_summary_score": float(sequence.get("energy_curve_summary_score", 0.0) or 0.0),
        "layout_search_summary_score": float(((reports.get("layout_search_report.json") or {}).get("summary") or {}).get("summary_score", 0.0) or 0.0),
        "storefront_summary_score": float((reports.get("storefront_optimization_report.json") or {}).get("summary_score", 0.0) or 0.0),
        "character_commercial_summary_score": float((reports.get("character_commercial_report.json") or {}).get("summary_score", 0.0) or 0.0),
        "dual_audience_summary_score": float((reports.get("dual_audience_report.json") or {}).get("summary_score", 0.0) or 0.0),
        "page_turn_tension_summary_score": float((reports.get("page_turn_tension_report.json") or {}).get("summary_score", 0.0) or 0.0),
    }

    actions_taken = {
        "reselection": reports.get("reselection_report.json") or {"enabled": False, "message": "Unavailable."},
        "targeted_regeneration": reports.get("targeted_regeneration_report.json") or {"enabled": False, "message": "Unavailable."},
        "sequence_optimization": reports.get("sequence_optimization_report.json") or {"enabled": False, "message": "Unavailable."},
        "layout_search": reports.get("layout_search_report.json") or {"enabled": False, "message": "Unavailable."},
    }

    sequence_findings = {
        "weak_clusters": sequence.get("weak_clusters", []),
        "color_transitions": sequence.get("color_transitions", []),
        "architecture_flow": sequence.get("architecture_flow", {}),
        "energy_curve": sequence.get("energy_curve", {}),
        "camera_sequence": sequence.get("camera_sequence", {}),
        "saliency_flow_sequence": sequence.get("saliency_flow_sequence", {}),
        "typography_sequence": sequence.get("typography_sequence", reports.get("typography_report.json") or {}),
        "hidden_world_sequence": sequence.get("hidden_world_sequence", reports.get("hidden_world_report.json") or {}),
        "dual_audience_summary": sequence.get("dual_audience_summary", reports.get("dual_audience_report.json") or {}),
        "page_turn_tension_summary": sequence.get("page_turn_tension_summary", reports.get("page_turn_tension_report.json") or {}),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact": MASTER_ARTIFACT_NAME,
        "summary_scores": summary_scores,
        "summary_notes": _as_list_of_strings(sequence.get("summary_notes", [])),
        "warnings": warnings,
        "limitations": limitations,
        "per_page_notes": sequence.get("per_page_notes", []),
        "sequence_findings": sequence_findings,
        "actions_taken": actions_taken,
        "legacy_artifacts": {
            "deprecated": LEGACY_ARTIFACTS,
            "retained_for_compatibility": [name for name in LEGACY_ARTIFACTS if reports.get(name) is not None],
            "migration": "Master report is authoritative; legacy reports are compatibility inputs.",
        },
    }


def validate_book_quality_report(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for field in [
        "schema_version",
        "generated_at",
        "artifact",
        "summary_scores",
        "warnings",
        "limitations",
        "per_page_notes",
        "sequence_findings",
        "actions_taken",
        "legacy_artifacts",
    ]:
        if field not in payload:
            failures.append(f"book_quality_report.json missing {field}")
    summary = payload.get("summary_scores", {})
    if isinstance(summary, dict):
        for field in ["overall_sequence_score", "color_flow_summary_score", "architecture_flow_summary_score", "energy_curve_summary_score"]:
            if field not in summary:
                failures.append(f"book_quality_report.json summary_scores missing {field}")
    else:
        failures.append("book_quality_report.json summary_scores must be an object")
    return failures


def write_book_quality_report(path: Path, payload: Dict[str, Any]) -> None:
    write_json(path, payload)
