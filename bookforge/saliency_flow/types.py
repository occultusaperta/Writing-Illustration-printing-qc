from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class SaliencyPeak:
    rank: int
    x: float
    y: float
    strength: float
    zone_hint: str


@dataclass(frozen=True)
class SaliencyFlowResult:
    map_shape: List[int]
    peaks: List[SaliencyPeak]
    first_fixation: SaliencyPeak | None
    center_of_mass: Dict[str, float]
    directional_energy: Dict[str, float]
    confidence: float
    warnings: List[str]
    notes: List[str]


@dataclass(frozen=True)
class TextZoneQuietnessResult:
    text_zone_present: bool
    mean_saliency: float
    surrounding_mean_saliency: float
    quietness_score: float
    warnings: List[str]


@dataclass(frozen=True)
class PageTurnFlowResult:
    applicable: bool
    rightward_pull: float
    leftward_pull: float
    page_turn_flow_score: float
    warnings: List[str]
    notes: List[str]


@dataclass(frozen=True)
class SpreadBridgeResult:
    applicable: bool
    bridge_score: float
    gutter_energy: float
    left_edge_energy: float
    right_edge_energy: float
    gutter_risk: float
    warnings: List[str]


@dataclass(frozen=True)
class SaliencyFlowScoreResult:
    primary_focus_score: float
    text_quietness_score: float
    page_turn_flow_score: float
    spread_bridge_score: float
    fixation_order_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]
    peak_summaries: List[SaliencyPeak]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SaliencySequenceFinding:
    summary_score: float
    weak_first_fixation_runs: List[str]
    text_busyness_runs: List[str]
    page_turn_resistance_runs: List[str]
    spread_bridge_failures: List[str]
    over_centralized_saliency_runs: List[str]
    camera_mismatch_warnings: List[str]
    positive_flow_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
