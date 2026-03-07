from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class PageTurnTensionScoreResult:
    rightward_vector_score: float
    incomplete_action_score: float
    cropped_continuation_score: float
    question_or_suspense_score: float
    lighting_pull_score: float
    turn_resistance_penalty: float
    page_turn_tension_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageTurnSequenceFinding:
    page: int
    page_turn_tension_score: float
    turn_resistance_penalty: float
    confidence: float
    notes: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageTurnTensionReport:
    enabled: bool
    summary_score: float
    weak_turn_runs: List[List[int]]
    leftward_resistance_runs: List[List[int]]
    over_resolved_turns: List[int]
    flat_page_turn_rhythm_clusters: List[List[int]]
    strong_turn_pages: List[int]
    climax_reveal_turn_support_pages: List[int]
    warnings: List[str]
    positive_notes: List[str]
    limitations: List[str]
    findings: List[PageTurnSequenceFinding]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
