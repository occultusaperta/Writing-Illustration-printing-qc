# Packet 9 — Bounded Reselection

`BOOKFORGE_RESELECTION=true` enables a conservative reselection pass after `review/book_sequence_report.json` is generated.

## What it does

- Uses existing candidate metadata from:
  - color score (Packet 3)
  - visual ensemble (Packet 5)
  - page architecture score (Packet 6)
  - sequence findings / weak clusters (Packet 8)
- Restricts eligibility to pages flagged by sequence diagnostics (or severe local metadata weakness).
- Compares current selected page vs already-generated runner-up candidates only.
- Requires measurable bounded composite improvement before replacement.
- Caps replacements per run (`max_reselections_per_run`, default `2`).
- Writes a fully auditable report to `review/reselection_report.json`.

## What it does not do

- No global Monte Carlo optimization.
- No open-ended search.
- No unbounded regeneration loops.
- No ranking pipeline replacement.
- No compositor or typography rewrite.

## Controls

- `BOOKFORGE_RESELECTION` (default disabled)
- `review.max_reselections_per_run` (default `2`)
- `review.minimum_required_improvement` (default `0.04`)
- `review.allow_reselection_regeneration` (default `false`, currently tracked but not used for unbounded search)

## How to inspect report

Inspect `review/reselection_report.json` for:

- `considered_pages` and `eligible_pages`
- `replaced_pages`
- `decisions[*].reason`
- `decisions[*].best_comparison` (before/after local+sequence composite scores)
- `sequence_improvement` (before/after sequence score delta if re-evaluated)
- `replacement_cap_hit`
