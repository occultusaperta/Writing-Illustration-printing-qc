from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class SequenceOptimizationConfig:
    enabled: bool
    max_pages_considered: int
    max_moves_per_run: int
    max_candidates_per_page: int
    minimum_net_improvement: float
    max_local_regression_tolerance: float
    opening_pages_protection: int
    climax_pages_protection: int
    ending_pages_protection: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SequenceOptimizationCandidate:
    page: int
    scope: str
    selected_candidate_path: str
    runner_up_candidate_path: str
    selected_candidate_id: str
    runner_up_candidate_id: str
    local_score_bundle: Dict[str, float]
    sequence_contribution_bundle: Dict[str, float]
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SequenceOptimizationMove:
    page: int
    candidate: SequenceOptimizationCandidate
    before_bundle: Dict[str, float]
    after_bundle: Dict[str, float]
    deltas: Dict[str, float]
    net_delta: float
    local_delta: float
    accepted: bool
    reason: str
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SequenceOptimizationDecision:
    page: int
    considered: bool
    accepted: bool
    selected_before: str
    selected_after: str
    reason: str
    best_move: SequenceOptimizationMove | None
    rejected_moves: List[SequenceOptimizationMove] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SequenceOptimizationImprovement:
    before_overall_sequence_score: float
    after_overall_sequence_score: float
    net_delta: float
    component_deltas: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SequenceOptimizationReport:
    enabled: bool
    config: Dict[str, Any]
    pages_considered: List[int]
    candidate_moves_considered: int
    accepted_moves: List[SequenceOptimizationMove]
    rejected_moves: List[SequenceOptimizationMove]
    decisions: List[SequenceOptimizationDecision]
    cap_hit: bool
    before_summary: Dict[str, float]
    after_summary: Dict[str, float]
    net_improvement: SequenceOptimizationImprovement
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
