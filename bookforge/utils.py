"""Shared utility helpers used across bookforge modules."""

from __future__ import annotations


def clamp01(value: float) -> float:
    """Clamp *value* to the closed interval [0.0, 1.0]."""
    return float(max(0.0, min(1.0, value)))


# ---------------------------------------------------------------------------
# Weakness-detection thresholds shared by reselection & targeted regeneration
# ---------------------------------------------------------------------------
PREMIUM_QC_WEAK_THRESHOLD: float = 0.78
COLOR_TRANSITION_WEAK_THRESHOLD: float = 0.72
SEVERE_COLOR_THRESHOLD: float = 0.68
SEVERE_ENSEMBLE_THRESHOLD: float = 0.70
SEVERE_ARCHITECTURE_THRESHOLD: float = 0.65
SEVERE_SALIENCY_THRESHOLD: float = 0.45
