from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class BabySchemaScoreResult:
    head_to_body_ratio_score: float
    eye_prominence_score: float
    face_roundness_score: float
    cheek_fullness_or_softness_score: float
    limb_shortness_softness_score: float
    overall_cuteness_proxy_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToyeticScoreResult:
    silhouette_distinctiveness_score: float
    signature_feature_score: float
    color_reproducibility_score: float
    angle_consistency_score: float
    plush_friendliness_score: float
    small_scale_recognizability_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SilhouetteScoreResult:
    subject_occupancy: float
    compactness_score: float
    edge_complexity_score: float
    distinguishability_score: float
    iconic_readability_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]
    diagnostics: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CharacterCommercialScoreResult:
    baby_schema: BabySchemaScoreResult
    toyetic: ToyeticScoreResult
    silhouette: SilhouetteScoreResult
    lead_character_strength_score: float
    recognizability_score: float
    plush_series_readiness_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CharacterSequenceFinding:
    page: int
    composite_score: float
    baby_schema_score: float
    toyetic_score: float
    silhouette_score: float
    confidence: float
    notes: List[str]
    warnings: List[str]


@dataclass(frozen=True)
class CharacterCommercialReport:
    enabled: bool
    summary_score: float
    lead_character_strength_summary: str
    strongest_pages: List[CharacterSequenceFinding]
    weakest_pages: List[CharacterSequenceFinding]
    consistency_notes: List[str]
    warnings: List[str]
    positive_notes: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
