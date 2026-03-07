from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List


class ShotType(str, Enum):
    ESTABLISHING_WIDE = "establishing_wide"
    MEDIUM_INTERACTION = "medium_interaction"
    CLOSEUP_EMOTION = "closeup_emotion"
    EXTREME_CLOSEUP_DETAIL = "extreme_closeup_detail"
    BIRDS_EYE = "birds_eye"
    WORMS_EYE = "worms_eye"
    OVER_SHOULDER = "over_shoulder"
    DUTCH_TILT = "dutch_tilt"


@dataclass(frozen=True)
class ShotPlanEntry:
    page_number: int
    spread_number: int | None
    shot_type: ShotType
    narrative_reason: str
    target_distance_class: str
    target_angle_class: str
    target_subject_focus: str
    sequence_priority: float
    confidence: float
    planning_notes: List[str]


@dataclass(frozen=True)
class ShotSequencePlan:
    pages: List[ShotPlanEntry]
    sequence_notes: List[str]
    diversity_score: float


@dataclass(frozen=True)
class ShotScoreResult:
    shot_type: str
    framing_scale_score: float
    focus_alignment_score: float
    angle_alignment_score: float
    family_match_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShotSequenceFinding:
    summary_score: float
    adjacent_repeat_warnings: List[str]
    medium_run_warnings: List[str]
    progression_warnings: List[str]
    opening_warnings: List[str]
    climax_warnings: List[str]
    ending_warnings: List[str]
    repetitive_run_warnings: List[str]



def to_primitive(payload: Any) -> Any:
    if isinstance(payload, Enum):
        return payload.value
    if isinstance(payload, list):
        return [to_primitive(i) for i in payload]
    if isinstance(payload, dict):
        return {k: to_primitive(v) for k, v in payload.items()}
    if hasattr(payload, "__dataclass_fields__"):
        return {k: to_primitive(v) for k, v in asdict(payload).items()}
    return payload
