from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class TypographyDirective:
    kind: str
    text: str
    role: str
    line_index: int
    strength: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TypographySpan:
    text: str
    role: str
    emphasis: float
    scale_class: str
    weight_class: str
    directional_drift: str = "none"
    preserve_exact_text: bool = True


@dataclass(frozen=True)
class TypographyLinePlan:
    line_text: str
    role: str
    alignment: str
    scale_class: str
    weight_class: str
    line_gap_multiplier: float = 1.0
    spans: List[TypographySpan] = field(default_factory=list)


@dataclass(frozen=True)
class PageTypographyPlan:
    page_number: int
    source_markdown: str
    text_zone: Dict[str, float]
    alignment: str
    preferred_region: str
    body_scale_class: str
    style_roles: List[str]
    lines: List[TypographyLinePlan]
    directives: List[TypographyDirective]
    quietness_requirement: float
    contrast_requirement: float
    overflow_expected: bool
    special_positioning_mode: str
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TypographyScoreResult:
    contrast_readability_score: float
    text_zone_quietness_score: float
    fit_score: float
    expressive_alignment_score: float
    readaloud_rhythm_score: float
    print_safety_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TypographySequenceFinding:
    summary_score: float
    high_quality_pages: List[int]
    crowding_risk_pages: List[int]
    weak_contrast_pages: List[int]
    overreach_pages: List[int]
    reveal_success_pages: List[int]
    fallback_pages: List[int]
    sequence_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
