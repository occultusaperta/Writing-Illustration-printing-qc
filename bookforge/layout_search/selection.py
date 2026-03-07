from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence, Tuple

from bookforge.layout_search.sampler import generate_layout_permutations
from bookforge.layout_search.scoring import score_layout_permutation
from bookforge.layout_search.types import (
    LayoutPermutation,
    LayoutPermutationScore,
    LayoutSearchConfig,
    LayoutSearchResult,
    LayoutSearchSequenceNote,
)


def _variant_swap_candidates(architecture_variants: Dict[str, Dict[str, Any]], architecture_type: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in architecture_variants.values():
        if str(row.get("architecture_type", "")) != architecture_type:
            continue
        zones = row.get("zones", []) if isinstance(row.get("zones", []), list) else []
        text_zone = next((z for z in zones if isinstance(z, dict) and z.get("zone_id") in {"text", "caption"}), None)
        art_zone = next((z for z in zones if isinstance(z, dict) and z.get("zone_id") == "art"), None)
        if not text_zone:
            continue
        out.append(
            {
                "variant_id": str(row.get("variant_id", "")),
                "text_zone": {k: float(text_zone.get(k, 0.0)) for k in ["x", "y", "w", "h"]},
                "art_zone": {k: float((art_zone or {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}).get(k, 0.0)) for k in ["x", "y", "w", "h"]},
            }
        )
    return out


def select_best_layout(
    *,
    page_numbers: Sequence[int],
    base_layout: Dict[str, Any],
    image_path: Path,
    page_text: str,
    config: LayoutSearchConfig,
    seed: int,
    is_spread: bool,
    architecture_variants: Dict[str, Dict[str, Any]] | None = None,
) -> LayoutSearchResult:
    architecture_type = str(base_layout.get("architecture_type", "none"))
    swaps = _variant_swap_candidates(architecture_variants or {}, architecture_type)
    permutations = generate_layout_permutations(
        page_numbers=page_numbers,
        base_layout=base_layout,
        config=config,
        seed=seed,
        is_spread=is_spread,
        variant_candidates=swaps,
    )
    scores: List[Tuple[LayoutPermutation, LayoutPermutationScore]] = []
    for perm in permutations:
        score = score_layout_permutation(
            perm,
            image_path=image_path,
            page_text=page_text,
            base_layout=base_layout,
            page_number=int(page_numbers[0]),
            is_spread=is_spread,
            gutter_sensitive=bool(base_layout.get("gutter_sensitive", False)),
        )
        scores.append((perm, score))

    valid = [(p, s) for p, s in scores if not s.rejected]
    chosen_perm, chosen_score = max(valid or scores, key=lambda row: row[1].composite_score)
    rejected_count = sum(1 for _, s in scores if s.rejected)

    selected_layout = dict(base_layout)
    selected_layout["text_zone"] = chosen_perm.text_zone
    selected_layout["art_zone"] = chosen_perm.art_zone
    selected_layout["panel_zones"] = chosen_perm.panel_zones
    selected_layout["inset_zones"] = chosen_perm.inset_zones
    selected_layout["reserve_whitespace"] = chosen_perm.reserve_whitespace
    selected_layout["variant_id"] = chosen_perm.variant_id
    selected_layout["layout_search"] = {
        "chosen_permutation_id": chosen_perm.permutation_id,
        "top_score": chosen_score.composite_score,
        "confidence": chosen_score.confidence,
        "explored_count": len(scores),
        "rejected_count": rejected_count,
    }

    rankings = [
        {
            "permutation": p.to_dict(),
            "score": s.to_dict(),
        }
        for p, s in sorted(scores, key=lambda row: row[1].composite_score, reverse=True)
    ]

    warnings = list(chosen_score.warnings)
    if not valid:
        warnings.append("all_permutations_failed_hard_constraints_using_best_available")
    return LayoutSearchResult(
        page_numbers=tuple(int(x) for x in page_numbers),
        scope="spread" if is_spread else "page",
        explored_count=len(scores),
        rejected_count=rejected_count,
        chosen_permutation_id=chosen_perm.permutation_id,
        top_score=chosen_score.composite_score,
        selected_layout=selected_layout,
        rankings=rankings,
        warnings=warnings,
        notes=list(chosen_score.notes),
    )


def build_layout_search_report(results: Sequence[LayoutSearchResult]) -> Dict[str, Any]:
    rows = [r.to_dict() for r in results]
    sorted_rows = sorted(rows, key=lambda r: float(r.get("top_score", 0.0) or 0.0))
    weakest = sorted_rows[: min(5, len(sorted_rows))]
    strongest = list(reversed(sorted_rows[-min(5, len(sorted_rows)) :]))
    repeated_weak: List[LayoutSearchSequenceNote] = []
    for row in rows:
        if float(row.get("top_score", 0.0) or 0.0) < 0.55:
            pages = row.get("page_numbers", [])
            repeated_weak.append(
                LayoutSearchSequenceNote(
                    page=int(pages[0]) if pages else 0,
                    severity="warning",
                    message="Weak local layout score; consider targeted regeneration if visual intent allows.",
                )
            )

    return {
        "status": "PASS",
        "summary": {
            "entries": len(rows),
            "mean_top_score": round(mean([float(r.get("top_score", 0.0) or 0.0) for r in rows]) if rows else 0.0, 4),
            "mean_explored": round(mean([int(r.get("explored_count", 0) or 0) for r in rows]) if rows else 0.0, 3),
            "total_rejected": int(sum(int(r.get("rejected_count", 0) or 0) for r in rows)),
            "notes": ["Bounded Monte Carlo local layout exploration applied before final render."],
        },
        "pages": rows,
        "weakest_pages": weakest,
        "strongest_pages": strongest,
        "sequence_notes": [asdict(n) for n in repeated_weak],
    }
