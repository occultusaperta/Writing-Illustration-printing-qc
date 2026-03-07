from __future__ import annotations

from typing import Any, Dict

from bookforge.dual_audience.adult_channel import score_adult_channel
from bookforge.dual_audience.child_channel import score_child_channel
from bookforge.dual_audience.types import DualAudienceScoreResult


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def score_dual_audience(
    report: Dict[str, Any],
    *,
    minimum_channel_threshold: float = 0.3,
) -> DualAudienceScoreResult:
    metadata = report.get("metadata", {}) if isinstance(report.get("metadata", {}), dict) else {}
    child = score_child_channel(report, metadata)
    adult = score_adult_channel(report, metadata)

    divergence = abs(child.composite_score - adult.composite_score)
    balance_score = _clamp01(1.0 - (divergence / 0.6))
    balance_penalty = _clamp01(max(0.0, divergence - 0.2) * 0.5)

    base = 0.52 * child.composite_score + 0.48 * adult.composite_score
    threshold_penalty = 0.0
    warnings: list[str] = []
    notes: list[str] = []
    if child.composite_score < minimum_channel_threshold:
        warnings.append("dual_audience_hard_warning_child_channel_below_threshold")
        threshold_penalty += 0.12
    if adult.composite_score < minimum_channel_threshold:
        warnings.append("dual_audience_hard_warning_adult_channel_below_threshold")
        threshold_penalty += 0.12
    if divergence > 0.35:
        warnings.append("dual_audience_channel_imbalance_warning")
    if balance_score > 0.8:
        notes.append("Child/adult channels are reasonably balanced.")

    composite = _clamp01(base + 0.06 * balance_score - balance_penalty - threshold_penalty)
    recommend_reject = bool(child.composite_score < 0.22 and adult.composite_score < 0.22)
    if recommend_reject:
        warnings.append("dual_audience_recommend_reject_both_channels_very_weak")

    limitations = [
        "Dual-audience scoring is bounded heuristic proxy scoring only.",
        "Does not claim true child testing or parent preference certainty.",
        "Used as an additive quality layer; not a standalone decision system.",
    ]
    confidence = _clamp01(0.45 + 0.25 * min(child.confidence, adult.confidence) + 0.2 * ((child.confidence + adult.confidence) / 2.0) + 0.1 * balance_score)

    warnings.extend(child.warnings)
    warnings.extend(adult.warnings)
    notes.extend(child.notes)
    notes.extend(adult.notes)

    return DualAudienceScoreResult(
        child_channel_score=child,
        adult_channel_score=adult,
        balance_score=round(balance_score, 4),
        divergence=round(divergence, 4),
        balance_penalty=round(balance_penalty, 4),
        minimum_channel_threshold=round(minimum_channel_threshold, 4),
        composite_score=round(composite, 4),
        recommend_reject=recommend_reject,
        confidence=round(confidence, 4),
        warnings=warnings,
        notes=notes,
        limitations=limitations,
    )
