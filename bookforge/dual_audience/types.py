from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ChildChannelScoreResult:
    focal_clarity_score: float
    face_action_prominence_score: float
    emotional_readability_score: float
    narrative_simplicity_score: float
    text_coexistence_safety_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdultChannelScoreResult:
    composition_maturity_score: float
    color_harmony_mood_score: float
    aesthetic_polish_score: float
    emotional_nuance_score: float
    reread_value_background_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DualAudienceScoreResult:
    child_channel_score: ChildChannelScoreResult
    adult_channel_score: AdultChannelScoreResult
    balance_score: float
    divergence: float
    balance_penalty: float
    minimum_channel_threshold: float
    composite_score: float
    recommend_reject: bool
    confidence: float
    warnings: List[str]
    notes: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DualAudienceSequenceFinding:
    page: int
    child_channel_score: float
    adult_channel_score: float
    balance_score: float
    composite_score: float
    confidence: float
    notes: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DualAudienceReport:
    enabled: bool
    summary_score: float
    child_channel_summary_score: float
    adult_channel_summary_score: float
    balance_summary_score: float
    strongest_pages: List[DualAudienceSequenceFinding]
    weakest_pages: List[DualAudienceSequenceFinding]
    child_confusion_risk_pages: List[int]
    adult_flatness_risk_pages: List[int]
    imbalance_pages: List[int]
    positive_notes: List[str]
    warnings: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
