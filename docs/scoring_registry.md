# Scoring Registry Tuning

`bookforge/scoring_registry.py` is the single source of truth for scoring weights, thresholds, transition targets, tie-break influence, and packet-level feature-flag defaults.

## What to tune

- `transition_targets`: hard-cut/blend drift targets used in sequence and reselection scoring.
- `feature_flag_defaults`: default values used when packet env flags are unset.
- `image_qc_ranking`: local candidate ranking penalties and weak tie-break influences.
- `sequence_review.overall_weights`: final book-level score blend.
- `local_candidate`: reselection and sequence-optimizer local/sequence weighting.
- `thresholds`: acceptance/rejection cutoffs for reselection, regeneration, and dual-audience minimums.
- packet-specific composites:
  - `camera_language`
  - `saliency_flow`
  - `page_architecture`
  - `typography`
  - `hidden_world`
  - `page_turn`
  - `dual_audience`

## Guidance

1. Prefer editing registry constants, not packet modules.
2. Keep weights normalized near prior behavior unless intentionally recalibrating.
3. Update/add regression tests in `tests/test_scoring_registry.py` for any changed default.
4. Use environment overrides for runtime feature-flag toggles; defaults are only fallback behavior.
