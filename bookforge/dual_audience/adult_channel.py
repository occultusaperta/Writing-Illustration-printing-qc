from __future__ import annotations

from typing import Any, Dict, Tuple

from bookforge.dual_audience.types import AdultChannelScoreResult


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _composition_maturity(metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    ensemble = ((metadata.get("visual_ensemble") or {}).get("critic_scores", {})) if isinstance((metadata.get("visual_ensemble") or {}).get("critic_scores", {}), dict) else {}
    arch = (metadata.get("page_architecture_score") or {}) if isinstance(metadata.get("page_architecture_score"), dict) else {}
    shot = (metadata.get("shot_adherence_score") or {}) if isinstance(metadata.get("shot_adherence_score"), dict) else {}
    composition = float(ensemble.get("composition_score", 0.5) or 0.5)
    architecture = float(arch.get("composite_score", 0.5) or 0.5)
    shot_score = float(shot.get("composite_score", 0.5) or 0.5)
    score = _clamp01(0.42 * composition + 0.36 * architecture + 0.22 * shot_score)
    if score < 0.45:
        warnings.append("adult_composition_maturity_weak")
    else:
        notes.append("Composition maturity proxies are supportive.")
    return score, warnings, notes


def _color_harmony(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    color = (metadata.get("color_score") or {}) if isinstance(metadata.get("color_score"), dict) else {}
    color_comp = float(color.get("composite_score", 0.5) or 0.5)
    drift = float(report.get("page_to_page_hist_drift", 0.0) or 0.0)
    style = float(report.get("style_hist_similarity", 0.5) or 0.5)
    score = _clamp01(0.5 * color_comp + 0.25 * style + 0.25 * (1.0 - min(1.0, drift * 1.4)))
    if score < 0.45:
        warnings.append("adult_color_mood_coherence_weak")
    return score, warnings, notes


def _aesthetic_polish(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    ensemble = ((metadata.get("visual_ensemble") or {}).get("critic_scores", {})) if isinstance((metadata.get("visual_ensemble") or {}).get("critic_scores", {}), dict) else {}
    ensemble_score = float((metadata.get("visual_ensemble") or {}).get("ensemble_score", 0.5) or 0.5)
    texture = float(ensemble.get("texture_score", 0.5) or 0.5)
    artifacts = float(ensemble.get("artifact_score", 0.5) or 0.5)
    perceptual = float(ensemble.get("perceptual_quality", 0.5) or 0.5)
    border_artifact = float(report.get("border_artifact_score", 0.0) or 0.0)
    score = _clamp01(0.33 * ensemble_score + 0.22 * texture + 0.22 * artifacts + 0.18 * perceptual + 0.05 * (1.0 - min(1.0, border_artifact * 2.0)))
    if score < 0.45:
        warnings.append("adult_aesthetic_polish_flat")
    return score, warnings, notes


def _emotional_nuance(metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    hidden = (metadata.get("hidden_world_score") or {}) if isinstance(metadata.get("hidden_world_score"), dict) else {}
    saliency = (metadata.get("saliency_flow_score") or {}) if isinstance(metadata.get("saliency_flow_score"), dict) else {}
    shot = (metadata.get("shot_adherence_score") or {}) if isinstance(metadata.get("shot_adherence_score"), dict) else {}
    subtle = float(hidden.get("subtlety_score", 0.5) or 0.5)
    foreshadow = float(hidden.get("foreshadowing_callback_score", 0.5) or 0.5)
    fixation = float(saliency.get("fixation_order_score", 0.5) or 0.5)
    angle = float(shot.get("angle_alignment_score", 0.5) or 0.5)
    score = _clamp01(0.35 * subtle + 0.25 * foreshadow + 0.2 * fixation + 0.2 * angle)
    if score < 0.45:
        warnings.append("adult_emotional_nuance_limited")
    else:
        notes.append("Secondary emotional signals are present.")
    return score, warnings, notes


def _reread_value(metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    hidden = (metadata.get("hidden_world_score") or {}) if isinstance(metadata.get("hidden_world_score"), dict) else {}
    parent_reward = float(hidden.get("parent_reward_score", 0.5) or 0.5)
    recurrence = float(hidden.get("recurrence_consistency_score", 0.5) or 0.5)
    hidden_comp = float(hidden.get("composite_score", 0.5) or 0.5)
    score = _clamp01(0.4 * hidden_comp + 0.35 * parent_reward + 0.25 * recurrence)
    if score < 0.45:
        warnings.append("adult_reread_value_weak")
    else:
        notes.append("Background/reward signals suggest reread value.")
    return score, warnings, notes


def score_adult_channel(report: Dict[str, Any], metadata: Dict[str, Any]) -> AdultChannelScoreResult:
    limitations = [
        "Heuristic proxy scoring only; this does not claim parent-preference certainty.",
        "Scores are additive and auditable, not a replacement for human art direction review.",
    ]
    composition, w1, n1 = _composition_maturity(metadata)
    color, w2, n2 = _color_harmony(report, metadata)
    polish, w3, n3 = _aesthetic_polish(report, metadata)
    nuance, w4, n4 = _emotional_nuance(metadata)
    reread, w5, n5 = _reread_value(metadata)

    composite = _clamp01(0.26 * composition + 0.2 * color + 0.24 * polish + 0.15 * nuance + 0.15 * reread)
    confidence = _clamp01(0.45 + 0.12 * bool(metadata.get("visual_ensemble")) + 0.12 * bool(metadata.get("color_score")) + 0.14 * bool(metadata.get("hidden_world_score")) + 0.08 * bool(metadata.get("shot_adherence_score")) + 0.09 * bool(report.get("style_hist_similarity")))

    return AdultChannelScoreResult(
        composition_maturity_score=round(composition, 4),
        color_harmony_mood_score=round(color, 4),
        aesthetic_polish_score=round(polish, 4),
        emotional_nuance_score=round(nuance, 4),
        reread_value_background_score=round(reread, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=w1 + w2 + w3 + w4 + w5,
        notes=n1 + n2 + n3 + n4 + n5,
        limitations=limitations,
    )
