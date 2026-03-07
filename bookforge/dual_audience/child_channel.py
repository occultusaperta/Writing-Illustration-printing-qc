from __future__ import annotations

from typing import Any, Dict, Tuple

from bookforge.dual_audience.types import ChildChannelScoreResult
from bookforge.utils import clamp01


def _focal_clarity(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    saliency = (metadata.get("saliency_flow_score") or {}) if isinstance(metadata.get("saliency_flow_score"), dict) else {}
    saliency_score = float(saliency.get("primary_focus_score", saliency.get("composite_score", 0.5)) or 0.5)
    fixation = float(saliency.get("fixation_order_score", 0.5) or 0.5)
    focus_overlap = float(report.get("focus_bleed_overlap", 0.0) or 0.0)
    score = clamp01(0.55 * saliency_score + 0.25 * fixation + 0.2 * (1.0 - min(1.0, focus_overlap * 2.0)))
    if score < 0.45:
        warnings.append("child_focal_clarity_weak")
    else:
        notes.append("Primary focal readability appears bounded and clear.")
    return score, warnings, notes


def _face_action_prominence(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    faces = float(report.get("face_like_regions", 0.0) or 0.0)
    saliency = (metadata.get("saliency_flow_score") or {}) if isinstance(metadata.get("saliency_flow_score"), dict) else {}
    first_fix = float(saliency.get("primary_focus_score", 0.5) or 0.5)
    face_component = 0.85 if 1 <= faces <= 2 else (0.55 if faces == 0 else 0.45)
    score = clamp01(0.65 * face_component + 0.35 * first_fix)
    if faces > 3:
        warnings.append("child_face_action_signal_noisy")
    if faces == 0:
        notes.append("No strong face-like signal; score falls back to focal-action proxy.")
    return score, warnings, notes


def _emotional_readability(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    shot = (metadata.get("shot_adherence_score") or {}) if isinstance(metadata.get("shot_adherence_score"), dict) else {}
    shot_type = str(shot.get("shot_type", ""))
    framing = float(shot.get("framing_scale_score", 0.5) or 0.5)
    saliency = (metadata.get("saliency_flow_score") or {}) if isinstance(metadata.get("saliency_flow_score"), dict) else {}
    focus = float(saliency.get("primary_focus_score", saliency.get("composite_score", 0.5)) or 0.5)
    boost = 0.08 if shot_type in {"closeup_emotion", "medium_interaction"} else 0.0
    score = clamp01(0.52 * focus + 0.38 * framing + 0.1 + boost)
    if score < 0.5:
        warnings.append("child_emotion_readability_muddy")
    else:
        notes.append("Emotion readability estimated via framing and focal proxies.")
    return score, warnings, notes


def _narrative_simplicity(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    ensemble = ((metadata.get("visual_ensemble") or {}).get("critic_scores", {})) if isinstance((metadata.get("visual_ensemble") or {}).get("critic_scores", {}), dict) else {}
    composition = float(ensemble.get("composition_score", 0.5) or 0.5)
    clarity = float(ensemble.get("clarity_score", 0.5) or 0.5)
    entropy = float(report.get("entropy", 6.0) or 6.0)
    clutter_penalty = clamp01((entropy - 6.2) / 2.6)
    score = clamp01(0.38 * composition + 0.32 * clarity + 0.3 * (1.0 - clutter_penalty))
    if clutter_penalty > 0.6:
        warnings.append("child_narrative_clutter_risk")
    return score, warnings, notes


def _text_coexistence(report: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[float, list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    saliency = (metadata.get("saliency_flow_score") or {}) if isinstance(metadata.get("saliency_flow_score"), dict) else {}
    text_q = float(saliency.get("text_quietness_score", 0.5) or 0.5)
    text_like = float(report.get("text_likelihood", 0.0) or 0.0)
    focus_overlap = float(report.get("focus_bleed_overlap", 0.0) or 0.0)
    score = clamp01(0.5 * text_q + 0.3 * (1.0 - min(1.0, text_like * 2.0)) + 0.2 * (1.0 - min(1.0, focus_overlap * 2.0)))
    if score < 0.5:
        warnings.append("child_text_readaloud_coexistence_risk")
    else:
        notes.append("Text zone coexistence appears reasonably quiet.")
    return score, warnings, notes


def score_child_channel(report: Dict[str, Any], metadata: Dict[str, Any]) -> ChildChannelScoreResult:
    limitations = [
        "Heuristic proxy scoring only; this is not child-user testing.",
        "No claim of cognitive certainty about early-reader comprehension.",
    ]
    focal, w1, n1 = _focal_clarity(report, metadata)
    face, w2, n2 = _face_action_prominence(report, metadata)
    emotion, w3, n3 = _emotional_readability(report, metadata)
    simplicity, w4, n4 = _narrative_simplicity(report, metadata)
    text_safe, w5, n5 = _text_coexistence(report, metadata)

    composite = clamp01(0.27 * focal + 0.2 * face + 0.2 * emotion + 0.18 * simplicity + 0.15 * text_safe)
    confidence = clamp01(0.45 + 0.1 * bool(metadata.get("saliency_flow_score")) + 0.1 * bool(metadata.get("shot_adherence_score")) + 0.1 * bool(metadata.get("visual_ensemble")) + 0.1 * bool(report.get("focus_box")) + 0.15 * bool(report.get("entropy")))

    return ChildChannelScoreResult(
        focal_clarity_score=round(focal, 4),
        face_action_prominence_score=round(face, 4),
        emotional_readability_score=round(emotion, 4),
        narrative_simplicity_score=round(simplicity, 4),
        text_coexistence_safety_score=round(text_safe, 4),
        composite_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=w1 + w2 + w3 + w4 + w5,
        notes=n1 + n2 + n3 + n4 + n5,
        limitations=limitations,
    )
