# Packet 10 — Bounded Targeted Regeneration

`BOOKFORGE_TARGETED_REGENERATION` adds a conservative, one-pass fallback after Packet 9 reselection.

## What it does

- Identifies weak page-local targets that remain problematic after reselection.
- Builds bounded regeneration requests that preserve locked visual identity and planning guidance.
- Generates a small fixed number of replacement candidates.
- Re-scores using the existing stack (color, visual ensemble, page architecture, sequence support proxy).
- Applies replacements only when measurable improvement crosses `minimum_required_improvement`.

## Inputs used

- Packet 8 sequence diagnostics (`review/book_sequence_report.json`)
- Packet 9 reselection outcomes (`review/reselection_report.json`)
- Existing prompt contract and per-page prompts (`prompts.json`)
- Color/architecture planning guidance from preprod planning artifacts
- Visual lock references and locked negative prompt from `LOCK.json`
- Existing Storyweaver metadata/constraints

## How it differs from Packet 9

- Packet 9 only reselects from existing candidate pools.
- Packet 10 can generate **new** page-local candidates, but only for bounded eligible weak targets.

## What it does NOT do

- No global full-book Monte Carlo optimization
- No unbounded loops or retries
- No ranking pipeline replacement
- No gate bypass (approval/checkpoint remain unchanged)
- No typography/compositor rewrite

## Feature flags and conservative defaults

- `BOOKFORGE_TARGETED_REGENERATION=false` (default)
- Run-level lock config keys under `review`:
  - `max_regenerations_per_run` (default `1`)
  - `minimum_required_regeneration_improvement` (default `0.06`)
  - `variants_per_regeneration` (default `1`)
  - `allow_spread_regeneration` (default `false`)

## Review artifact

The run writes `review/targeted_regeneration_report.json` with:

- enabled/disabled state
- config used
- eligible and regenerated targets
- decisions and reasons
- local/sequence/composite before-vs-after comparisons
- accepted/rejected outcomes
- cap-hit indicator
- sequence re-evaluation summary
