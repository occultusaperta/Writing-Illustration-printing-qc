from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from bookforge.page_architecture.constants import SUITABILITY_MATRIX
from bookforge.page_architecture.energy import target_energy_curve
from bookforge.page_architecture.templates import architecture_templates
from bookforge.page_architecture.types import ArchitecturePlan, ArchitectureType, to_primitive


def _score_variant(narrative_function: str, energy: float, variant_id: str, arch_type: ArchitectureType) -> float:
    suitability = SUITABILITY_MATRIX.get(narrative_function, {}).get(arch_type.value, 0.5)
    energy_pref = 1.0 - abs(energy - suitability)
    return 0.7 * suitability + 0.3 * energy_pref


def plan_architecture_sequence(pages: List[Dict[str, object]], genre: str = "picture_book", beam_width: int = 3) -> tuple[List[ArchitecturePlan], Dict[str, object]]:
    templates = architecture_templates()
    narrative_functions = [str(p.get("narrative_function", "rising_action")) for p in pages]
    energies = target_energy_curve(narrative_functions, genre=genre)

    beam: List[Tuple[float, List[ArchitecturePlan], str]] = [(0.0, [], "")]
    for idx, page in enumerate(pages):
        page_no = int(page.get("page_number", idx + 1))
        fn = narrative_functions[idx]
        target_energy = energies[idx]
        next_beam: List[Tuple[float, List[ArchitecturePlan], str]] = []
        for score_so_far, seq, prev_arch in beam:
            for variant in templates:
                if prev_arch == ArchitectureType.WORDLESS_SPREAD.value and variant.architecture_type == ArchitectureType.WORDLESS_SPREAD:
                    continue
                local = _score_variant(fn, target_energy, variant.variant_id, variant.architecture_type)
                penalty = 0.06 if prev_arch == variant.architecture_type.value else 0.0
                total = score_so_far + local - penalty
                next_beam.append((total, seq + [ArchitecturePlan(page_no, fn, target_energy, variant.variant_id, variant.architecture_type, round(local - penalty, 4))], variant.architecture_type.value))
        beam = sorted(next_beam, key=lambda x: x[0], reverse=True)[:beam_width]
    best = beam[0] if beam else (0.0, [], "")
    report = {
        "beam_width": beam_width,
        "total_score": round(best[0], 4),
        "sequence_length": len(best[1]),
        "architecture_type_counts": _count_types(best[1]),
    }
    return best[1], report


def _count_types(plans: List[ArchitecturePlan]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for plan in plans:
        k = plan.selected_architecture_type.value
        counts[k] = counts.get(k, 0) + 1
    return counts


def write_planning_artifacts(base_dir: Path, plan: List[ArchitecturePlan], report: Dict[str, object]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "architecture_plan.json").write_text(json.dumps([to_primitive(p) for p in plan], indent=2), encoding="utf-8")
    (base_dir / "architecture_sequence_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
