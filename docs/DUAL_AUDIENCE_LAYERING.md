# Dual Audience Layering (Packet 19)

`BOOKFORGE_DUAL_AUDIENCE` (default: enabled) adds a bounded, deterministic proxy layer that scores each candidate image on two parallel channels:

- **Child channel**: focal clarity, face/action prominence, emotional readability, narrative simplicity, text coexistence safety.
- **Adult channel**: composition maturity, color/mood coherence, aesthetic polish, emotional nuance, reread/background value.

## Honesty and scope

This layer is **heuristic proxy scoring only**:

- It does **not** claim true child cognition testing.
- It does **not** claim true parent preference certainty.
- It is an **additive quality layer** for QA/ranking/review and is not a standalone art-direction authority.

## Candidate integration

During candidate QA (`bookforge/qc/image_qc.py`), each variant gets:

- `metadata.dual_audience_score`

The score is used as a **weak additive tie-breaker** in variant ranking and does not replace existing gate logic.

## Composite policy

`DualAudienceScoreResult` combines both channels with:

- weighted mean
- bounded balance score / divergence penalty
- hard warnings if either channel drops below `minimum_channel_threshold`
- optional reject recommendation only when both channels are extremely weak

This is recommendation-oriented and preserves existing pipeline hard-fail behavior.

## Review artifacts

The pipeline writes:

- `review/dual_audience_report.json`

And threads dual-audience summary into:

- `review/book_sequence_report.json` under `dual_audience_summary`
- per-page notes include child/adult/balance values

## Verify / package behavior

- `review/dual_audience_report.json` is included in package expectations.
- When dual-audience feature is enabled, malformed/missing required top-level fields fail verify.
- When disabled, absence of the report follows bounded no-op behavior (warning-only path).
