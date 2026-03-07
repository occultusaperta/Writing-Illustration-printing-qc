from __future__ import annotations

from pathlib import Path

from bookforge.character_scoring.baby_schema import score_baby_schema
from bookforge.character_scoring.silhouette import score_character_silhouette
from bookforge.character_scoring.toyetic import score_toyetic
from bookforge.character_scoring.types import CharacterCommercialScoreResult


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def score_character_commercial(image_path: str | Path) -> CharacterCommercialScoreResult:
    silhouette = score_character_silhouette(image_path)
    baby = score_baby_schema(image_path, generalized_mode=True)
    toyetic = score_toyetic(image_path, silhouette)

    lead_strength = _clamp01(0.52 * baby.composite_score + 0.48 * toyetic.composite_score)
    recognizability = _clamp01(0.55 * silhouette.distinguishability_score + 0.45 * toyetic.signature_feature_score)
    plush_series = _clamp01(0.5 * toyetic.plush_friendliness_score + 0.3 * silhouette.iconic_readability_score + 0.2 * toyetic.small_scale_recognizability_score)

    composite = _clamp01(0.38 * lead_strength + 0.34 * recognizability + 0.28 * plush_series)
    confidence = _clamp01(0.3 + 0.35 * baby.confidence + 0.35 * toyetic.confidence)

    warnings = list(dict.fromkeys(baby.warnings + toyetic.warnings + silhouette.warnings))
    notes = list(dict.fromkeys(baby.notes + toyetic.notes + silhouette.notes))

    return CharacterCommercialScoreResult(
        baby_schema=baby,
        toyetic=toyetic,
        silhouette=silhouette,
        lead_character_strength_score=round(lead_strength, 4),
        recognizability_score=round(recognizability, 4),
        plush_series_readiness_score=round(plush_series, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
    )


__all__ = [
    "score_character_commercial",
]
