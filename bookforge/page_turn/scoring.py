from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from bookforge.page_turn.types import PageTurnTensionScoreResult
from bookforge.utils import clamp01


def _safe_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_rgb(path: Path | str) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32)


def _gray(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _edge_energy(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return gx + gy


def _incomplete_text_cue_score(page_text: str, prompt_metadata: Dict[str, Any], illustration_notes: str) -> float:
    text = " ".join([_safe_text(page_text), _safe_text(illustration_notes), _safe_text(prompt_metadata.get("camera_context", "")), _safe_text(prompt_metadata.get("shot_type", ""))])
    if not text:
        return 0.5
    suspense_hits = sum(1 for token in ["?", "suddenly", "before", "wait", "about to", "mystery", "unknown", "next", "turn", "unseen", "cliffhanger", "reveal"] if token in text)
    resolved_hits = sum(1 for token in ["finally", "the end", "rest", "sleep", "resolved", "calm", "peaceful", "complete"] if token in text)
    score = 0.5 + 0.08 * suspense_hits - 0.1 * resolved_hits
    return clamp01(score)


def score_page_turn_tension(
    image: Path | str,
    *,
    page_number: int,
    page_count: int,
    page_text: str = "",
    prompt_metadata: Dict[str, Any] | None = None,
    architecture_variant: Dict[str, Any] | None = None,
    shot_plan_entry: Dict[str, Any] | None = None,
    saliency_score: Dict[str, Any] | None = None,
    illustration_notes: str = "",
) -> PageTurnTensionScoreResult:
    """Bounded heuristic proxy for page-turn momentum; this is not true semantic understanding."""

    prompt_metadata = _safe_dict(prompt_metadata)
    architecture_variant = _safe_dict(architecture_variant)
    shot_plan_entry = _safe_dict(shot_plan_entry)
    saliency_score = _safe_dict(saliency_score)

    arr = _load_rgb(image)
    gray = _gray(arr)
    h, w = gray.shape
    half = max(1, w // 2)
    edge = _edge_energy(gray)

    left_energy = float(np.mean(edge[:, :half])) if half > 0 else 0.0
    right_energy = float(np.mean(edge[:, half:])) if w - half > 0 else 0.0
    total_energy = max(1e-6, left_energy + right_energy)
    right_energy_ratio = right_energy / total_energy

    right_band = max(1, int(w * 0.16))
    left_band = max(1, int(w * 0.16))
    right_edge_density = float(np.mean(edge[:, w - right_band :]))
    left_edge_density = float(np.mean(edge[:, :left_band]))

    right_brightness = float(np.mean(gray[:, half:])) if w - half > 0 else float(np.mean(gray))
    left_brightness = float(np.mean(gray[:, :half])) if half > 0 else float(np.mean(gray))

    rightward_vector_score = clamp01(0.45 + 0.9 * (right_energy_ratio - 0.5))
    cropped_continuation_score = clamp01(0.35 + (right_edge_density / max(right_edge_density + left_edge_density, 1e-6)))

    saliency_comp = float(saliency_score.get("composite_score", 0.5) or 0.5)
    fixation = float(saliency_score.get("fixation_order_score", saliency_comp) or saliency_comp)
    shot_type = _safe_text(shot_plan_entry.get("shot_type", ""))
    action_hint = 0.1 if any(k in shot_type for k in ["action", "tracking", "dynamic", "closeup_emotion"]) else 0.0
    incomplete_action_score = clamp01(0.25 + 0.45 * saliency_comp + 0.2 * fixation + action_hint)

    question_or_suspense_score = _incomplete_text_cue_score(page_text, prompt_metadata, illustration_notes)

    light_delta = (right_brightness - left_brightness) / 255.0
    lighting_pull_score = clamp01(0.5 + 1.4 * light_delta)

    center = gray[:, max(0, int(w * 0.4)) : min(w, int(w * 0.6))]
    center_std = float(np.std(center)) if center.size else float(np.std(gray))
    closure_bias = 0.0
    if page_number >= max(1, page_count - 1):
        closure_bias = 0.12
    if page_number == page_count:
        closure_bias = 0.2
    architecture_type = _safe_text(architecture_variant.get("architecture_type", ""))
    if architecture_type == "text_dominant":
        closure_bias += 0.06

    left_pull = clamp01((left_energy - right_energy) / max(total_energy, 1e-6) + 0.5)
    central_deadness = clamp01(0.55 - center_std / 32.0)
    turn_resistance_penalty = clamp01(0.4 * left_pull + 0.25 * central_deadness + closure_bias)

    composite = clamp01(
        0.24 * rightward_vector_score
        + 0.17 * incomplete_action_score
        + 0.17 * cropped_continuation_score
        + 0.15 * question_or_suspense_score
        + 0.12 * lighting_pull_score
        - 0.2 * turn_resistance_penalty
    )

    evidence = [rightward_vector_score, cropped_continuation_score, lighting_pull_score, saliency_comp]
    confidence = clamp01(0.45 + 0.12 * sum(1 for v in evidence if 0.2 <= v <= 0.95))

    warnings: List[str] = []
    notes: List[str] = [
        "Page-turn tension uses bounded visual/textual heuristics as proxy signals, not narrative certainty.",
        "No eye-tracking or true motion understanding is performed.",
    ]
    if rightward_vector_score < 0.4:
        warnings.append("Weak rightward compositional pull proxy.")
    if turn_resistance_penalty > 0.6:
        warnings.append("High turn-resistance proxy (left pull or resolved closure).")
    if page_number == page_count:
        notes.append("Ending page detected; resolved closure is partially tolerated.")

    return PageTurnTensionScoreResult(
        rightward_vector_score=round(rightward_vector_score, 4),
        incomplete_action_score=round(incomplete_action_score, 4),
        cropped_continuation_score=round(cropped_continuation_score, 4),
        question_or_suspense_score=round(question_or_suspense_score, 4),
        lighting_pull_score=round(lighting_pull_score, 4),
        turn_resistance_penalty=round(turn_resistance_penalty, 4),
        page_turn_tension_score=round(composite, 4),
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
    )
