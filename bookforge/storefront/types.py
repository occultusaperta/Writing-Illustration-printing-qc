from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ThumbnailScoreResult:
    title_readability_score: float
    focal_clarity_score: float
    character_visibility_score: float
    contrast_at_thumbnail_score: float
    emotional_tone_clarity_score: float
    clutter_penalty: float
    clutter_score: float
    composite_score: float
    confidence: float
    warnings: List[str]
    notes: List[str]


@dataclass(frozen=True)
class CoverThumbnailDiagnostics:
    cover_path: str
    thumbnail_heights: List[int]
    per_size_scores: List[Dict[str, Any]]
    aggregate: ThumbnailScoreResult

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LookInsidePageScore:
    page_number: int
    image_path: str
    focal_strength_score: float
    saliency_flow_score: float
    typography_readability_score: float
    emotional_hook_score: float
    color_script_strength_score: float
    hidden_world_delight_score: float
    architecture_camera_strength_score: float
    composite_score: float
    warnings: List[str]
    notes: List[str]


@dataclass(frozen=True)
class StorefrontSequenceFinding:
    finding_type: str
    severity: str
    page_number: int | None
    message: str


@dataclass(frozen=True)
class LookInsideSequenceReport:
    priority_pages: List[int]
    page_scores: List[LookInsidePageScore]
    strongest_page: int | None
    weakest_page: int | None
    preview_segment_score: float
    positive_notes: List[str]
    warnings: List[str]
    findings: List[StorefrontSequenceFinding]


@dataclass(frozen=True)
class StorefrontOptimizationReport:
    enabled: bool
    cover_thumbnail: CoverThumbnailDiagnostics | None
    look_inside: LookInsideSequenceReport
    first_pages_strength_score: float
    summary_score: float
    warnings: List[str]
    notes: List[str]
    limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
