"""Shared utility helpers used across bookforge modules."""

from __future__ import annotations


def clamp01(value: float) -> float:
    """Clamp *value* to the closed interval [0.0, 1.0]."""
    return float(max(0.0, min(1.0, value)))
