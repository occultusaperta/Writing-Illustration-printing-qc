from bookforge.dual_audience.scoring import score_dual_audience
from bookforge.dual_audience.sequence import build_dual_audience_report, write_dual_audience_report
from bookforge.dual_audience.types import (
    AdultChannelScoreResult,
    ChildChannelScoreResult,
    DualAudienceReport,
    DualAudienceScoreResult,
    DualAudienceSequenceFinding,
)

__all__ = [
    "ChildChannelScoreResult",
    "AdultChannelScoreResult",
    "DualAudienceScoreResult",
    "DualAudienceSequenceFinding",
    "DualAudienceReport",
    "score_dual_audience",
    "build_dual_audience_report",
    "write_dual_audience_report",
]
