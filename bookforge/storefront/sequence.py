from __future__ import annotations

from typing import List

from bookforge.storefront.types import LookInsidePageScore, StorefrontSequenceFinding


def build_storefront_sequence_findings(page_scores: List[LookInsidePageScore]) -> List[StorefrontSequenceFinding]:
    findings: List[StorefrontSequenceFinding] = []
    for row in page_scores:
        if row.typography_readability_score < 0.42:
            findings.append(
                StorefrontSequenceFinding(
                    finding_type="typography",
                    severity="warning",
                    page_number=row.page_number,
                    message="Typography readability may underperform in Look Inside preview.",
                )
            )
        if row.focal_strength_score < 0.4 and row.saliency_flow_score < 0.42:
            findings.append(
                StorefrontSequenceFinding(
                    finding_type="staging",
                    severity="warning",
                    page_number=row.page_number,
                    message="Weak focal staging and saliency flow in preview-priority page.",
                )
            )
    return findings
