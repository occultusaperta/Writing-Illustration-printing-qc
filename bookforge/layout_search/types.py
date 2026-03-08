from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class LayoutPermutation:
    permutation_id: str
    page_numbers: Tuple[int, ...]
    architecture_type: str
    variant_id: str
    text_zone: Dict[str, float]
    art_zone: Dict[str, float]
    panel_zones: List[Dict[str, float]] = field(default_factory=list)
    inset_zones: List[Dict[str, float]] = field(default_factory=list)
    reserve_whitespace: List[Dict[str, float]] = field(default_factory=list)
    compositor_hints: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayoutPermutationScore:
    permutation_id: str
    text_readability_score: float
    text_fit_score: float
    saliency_quietness_score: float
    focal_balance_score: float
    gutter_safety_score: float
    whitespace_balance_score: float
    architecture_alignment_score: float
    page_turn_flow_score: float
    composite_score: float
    confidence: float
    rejected: bool
    warnings: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayoutSearchConfig:
    max_permutations_per_page: int = 8
    max_permutations_per_spread: int = 12
    random_seed: int = 1337
    enable_crop_shift: bool = True
    enable_text_zone_variation: bool = True
    enable_variant_swap_within_architecture: bool = True


@dataclass(frozen=True)
class LayoutSearchSequenceNote:
    page: int
    severity: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayoutSearchResult:
    page_numbers: Tuple[int, ...]
    scope: str
    explored_count: int
    rejected_count: int
    chosen_permutation_id: str
    top_score: float
    selected_layout: Dict[str, Any]
    rankings: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
