from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Tuple


@dataclass(frozen=True)
class TransitionTargetConfig:
    hard_cut_floor: float = 0.45
    hard_cut_strength_multiplier: float = 0.8
    blend_ceiling: float = 0.22
    blend_strength_multiplier: float = 0.45


@dataclass(frozen=True)
class FeatureFlagDefaults:
    values: Dict[str, str] = field(
        default_factory=lambda: {
            "BOOKFORGE_CHARACTER_COMMERCIAL_SCORING": "true",
            "BOOKFORGE_SALIENCY_FLOW": "true",
            "BOOKFORGE_DUAL_AUDIENCE": "true",
            "BOOKFORGE_PAGE_TURN_TENSION": "true",
        }
    )


@dataclass(frozen=True)
class ImageQCRankingConfig:
    quality_penalty_text: float = 4.0
    quality_penalty_watermark: float = 4.0
    quality_penalty_logo: float = 3.0
    quality_penalty_border_artifact: float = 3.0
    style_color_drift_penalty: float = 0.6
    brightness_penalty_weight: float = 0.2
    brightness_penalty_floor: float = 100.0
    out_of_gamut_penalty_weight: float = 5.0
    architecture_tiebreak_weight: float = 1.0
    shot_tiebreak_weight: float = 0.15
    saliency_tiebreak_weight: float = 0.05


@dataclass(frozen=True)
class SequenceReviewConfig:
    overall_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "color": 0.195,
            "architecture": 0.175,
            "energy_curve": 0.15,
            "camera": 0.11,
            "saliency": 0.1,
            "typography": 0.09,
            "hidden_world": 0.09,
            "dual_audience": 0.08,
            "page_turn": 0.01,
        }
    )


@dataclass(frozen=True)
class LocalCandidateConfig:
    reselection_local_weights: Dict[str, float] = field(
        default_factory=lambda: {"color": 0.37, "ensemble": 0.33, "architecture": 0.22, "saliency": 0.08}
    )
    reselection_sequence_support_weights: Dict[str, float] = field(
        default_factory=lambda: {"transition_fit": 0.5, "ensemble": 0.3, "architecture": 0.2}
    )
    reselection_composite_weights: Dict[str, float] = field(default_factory=lambda: {"local": 0.7, "sequence": 0.3})
    sequence_optimizer_local_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "color": 0.195,
            "ensemble": 0.175,
            "architecture": 0.155,
            "saliency": 0.11,
            "camera": 0.09,
            "hidden_world": 0.08,
            "character": 0.07,
            "typography": 0.03,
            "dual_audience": 0.08,
            "page_turn_tension": 0.015,
        }
    )
    sequence_optimizer_delta_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "color_flow_score": 0.13,
            "architecture_flow_score": 0.12,
            "camera_flow_score": 0.11,
            "saliency_flow_score": 0.14,
            "typography_sequence_score": 0.07,
            "hidden_world_continuity_score": 0.07,
            "storefront_opening_score": 0.07,
            "character_consistency_score": 0.08,
            "layout_search_support_score": 0.08,
            "weak_cluster_reduction_score": 0.12,
            "dual_audience_balance_score": 0.08,
            "page_turn_tension_summary_score": 0.03,
        }
    )


@dataclass(frozen=True)
class ThresholdConfig:
    reselection_premium_qc_min: float = 0.78
    reselection_transition_score_min: float = 0.72
    reselection_color_min: float = 0.68
    reselection_ensemble_min: float = 0.7
    reselection_architecture_min: float = 0.65
    reselection_saliency_min: float = 0.45
    targeted_regen_layout_conflict_overlap_max: float = 0.16
    targeted_regen_premium_qc_min: float = 0.76
    targeted_regen_transition_score_min: float = 0.70
    dual_audience_minimum_channel_threshold: float = 0.3


@dataclass(frozen=True)
class CameraLanguageConfig:
    default_focus_area_ratio: float = 0.25
    default_angle_score: float = 0.55
    tilted_angle_score: float = 0.6
    over_shoulder_angle_score: float = 0.65
    framing_focus_overlap_penalty: float = 2.0
    shot_weights: Dict[str, float] = field(default_factory=lambda: {"framing": 0.35, "focus": 0.3, "angle": 0.2, "family": 0.15})
    distance_ranges: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {"wide": (0.02, 0.22), "medium": (0.12, 0.45), "close": (0.32, 0.72), "extreme_close": (0.55, 1.0)})


@dataclass(frozen=True)
class SaliencyFlowConfig:
    no_first_fixation_score: float = 0.25
    no_fixation_order_score: float = 0.3
    not_applicable_page_turn_score: float = 0.5
    primary_focus_weights: Dict[str, float] = field(default_factory=lambda: {"in_art": 0.8, "not_in_art": 0.55})
    composite_weights: Dict[str, float] = field(default_factory=lambda: {"primary_focus": 0.30, "text_quietness": 0.20, "page_turn": 0.18, "spread_bridge": 0.16, "fixation_order": 0.16})


@dataclass(frozen=True)
class PageArchitectureConfig:
    composite_weights: Dict[str, float] = field(default_factory=lambda: {"readability": 0.35, "focal": 0.30, "fit": 0.20, "gutter": 0.15})


@dataclass(frozen=True)
class TypographyConfig:
    composite_weights: Dict[str, float] = field(default_factory=lambda: {"contrast": 0.2, "quietness": 0.18, "fit": 0.2, "expressive": 0.16, "rhythm": 0.14, "print_safety": 0.12})


@dataclass(frozen=True)
class HiddenWorldConfig:
    composite_weights: Dict[str, float] = field(default_factory=lambda: {"required_presence": 0.24, "recurrence": 0.18, "subtlety": 0.16, "parent_reward": 0.14, "foreshadow_callback": 0.14, "text_safety": 0.14})


@dataclass(frozen=True)
class PageTurnConfig:
    composite_weights: Dict[str, float] = field(default_factory=lambda: {"rightward_vector": 0.24, "incomplete_action": 0.17, "cropped_continuation": 0.17, "question_or_suspense": 0.15, "lighting_pull": 0.12, "turn_resistance_penalty": -0.2})


@dataclass(frozen=True)
class DualAudienceConfig:
    base_weights: Dict[str, float] = field(default_factory=lambda: {"child": 0.52, "adult": 0.48})
    balance_bonus_weight: float = 0.06


@dataclass(frozen=True)
class BookforgeScoringRegistry:
    transition_targets: TransitionTargetConfig = TransitionTargetConfig()
    feature_flag_defaults: FeatureFlagDefaults = FeatureFlagDefaults()
    image_qc_ranking: ImageQCRankingConfig = ImageQCRankingConfig()
    sequence_review: SequenceReviewConfig = SequenceReviewConfig()
    local_candidate: LocalCandidateConfig = LocalCandidateConfig()
    thresholds: ThresholdConfig = ThresholdConfig()
    camera_language: CameraLanguageConfig = CameraLanguageConfig()
    saliency_flow: SaliencyFlowConfig = SaliencyFlowConfig()
    page_architecture: PageArchitectureConfig = PageArchitectureConfig()
    typography: TypographyConfig = TypographyConfig()
    hidden_world: HiddenWorldConfig = HiddenWorldConfig()
    page_turn: PageTurnConfig = PageTurnConfig()
    dual_audience: DualAudienceConfig = DualAudienceConfig()


@lru_cache(maxsize=1)
def scoring_registry() -> BookforgeScoringRegistry:
    return BookforgeScoringRegistry()


def feature_flag_enabled(name: str) -> bool:
    defaults = scoring_registry().feature_flag_defaults.values
    default = defaults.get(name, "false")
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def transition_target(mode: str, strength: float) -> float:
    cfg = scoring_registry().transition_targets
    if mode == "hard_cut":
        return max(cfg.hard_cut_floor, strength * cfg.hard_cut_strength_multiplier)
    return min(cfg.blend_ceiling, strength * cfg.blend_strength_multiplier)
