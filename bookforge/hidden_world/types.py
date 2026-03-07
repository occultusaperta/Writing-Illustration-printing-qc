from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List


class HiddenDetailType(str, Enum):
    REQUIRED = "required"
    RECURRING_MOTIF = "recurring_motif"
    FORESHADOW = "foreshadow"
    CALLBACK = "callback"
    PARENT_REWARD = "parent_reward"


@dataclass(frozen=True)
class HiddenDetailPlan:
    detail_id: str
    detail_text: str
    detail_type: HiddenDetailType
    source: str
    page_numbers: List[int]
    visibility_target: str
    recurrence_expected: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageHiddenWorldPlan:
    page_number: int
    required_details: List[str]
    recurring_motifs: List[str]
    foreshadowing_hints: List[str]
    callback_hints: List[str]
    parent_reward_details: List[str]
    visibility_targets: Dict[str, str]
    discoverable_not_dominant: bool
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HiddenWorldSequencePlan:
    page_count: int
    recurring_motifs: List[str]
    detail_plans: List[HiddenDetailPlan]
    pages: List[PageHiddenWorldPlan]
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_count": self.page_count,
            "recurring_motifs": list(self.recurring_motifs),
            "detail_plans": [d.to_dict() for d in self.detail_plans],
            "pages": [p.to_dict() for p in self.pages],
            "warnings": list(self.warnings),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class HiddenWorldScoreResult:
    required_detail_presence_score: float
    recurrence_consistency_score: float
    subtlety_score: float
    parent_reward_score: float
    foreshadowing_callback_score: float
    text_collision_risk_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HiddenWorldSequenceFinding:
    summary_score: float
    recurring_motif_continuity_notes: List[str]
    weak_recurrence_stretches: List[str]
    over_obvious_warnings: List[str]
    too_dominant_warnings: List[str]
    likely_too_invisible_warnings: List[str]
    foreshadow_callback_notes: List[str]
    parent_reward_density_notes: List[str]
    positive_rereadability_highlights: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
