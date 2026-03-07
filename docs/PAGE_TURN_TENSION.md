# Page-Turn Tension Engineering (Packet 20)

`BOOKFORGE_PAGE_TURN_TENSION=true|false` (default: `true`)

Packet 20 adds a bounded, deterministic, additive heuristic layer for page-turn momentum. It is **not** true semantic motion understanding, eye-tracking certainty, or narrative certainty.

## What it does

1. **Candidate-level scoring** in QA:
   - attaches `metadata.page_turn_tension_score`
   - contributes a **weak additive tie-break** to candidate selection
2. **Sequence-level review**:
   - emits `review/page_turn_tension_report.json`
   - threads compact summary into `review/book_sequence_report.json` under `page_turn_tension_summary`
3. **Sequence optimizer compatibility**:
   - adds a small local signal (`page_turn_tension`) and sequence summary component (`page_turn_tension_summary_score`) in the move-scoring bundle
   - no additional search pass, no redesign

## Heuristic proxy signals

Per page candidate, the scorer estimates:

- `rightward_vector_score`
- `incomplete_action_score`
- `cropped_continuation_score`
- `question_or_suspense_score`
- `lighting_pull_score`
- `turn_resistance_penalty`

Composite output:

- `page_turn_tension_score`
- `confidence`
- `warnings`
- `notes`

## Disable behavior

When disabled, all packet behavior is safe no-op:

- candidate metadata is not attached
- review report is still written with `enabled=false` and zeroed summary fields
- verify/package checks remain deterministic

## Review artifact schema highlights

`review/page_turn_tension_report.json` includes:

- `enabled`
- `summary_score`
- `weak_turn_runs`
- `leftward_resistance_runs`
- `over_resolved_turns`
- `flat_page_turn_rhythm_clusters`
- `strong_turn_pages`
- `climax_reveal_turn_support_pages`
- `warnings`
- `positive_notes`
- `limitations`
- `findings`

