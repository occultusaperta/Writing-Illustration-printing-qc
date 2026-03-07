# Storefront Optimization (Packet 15)

Packet 15 adds a bounded, additive storefront-readiness layer focused on:

- cover performance at thumbnail sizes
- Look Inside opening-page strength
- review artifact visibility for storefront risk/quality

## Feature flag

- `BOOKFORGE_STOREFRONT_OPTIMIZATION=true|false` (default `true`)

When disabled, the pipeline emits a safe no-op storefront report with `enabled=false`.

## What is scored

### Cover thumbnail diagnostics

Generated from real cover images at small target heights (default: `100`, `128`, `160` px):

- `title_readability_score`
- `focal_clarity_score`
- `character_visibility_score`
- `contrast_at_thumbnail_score`
- `emotional_tone_clarity_score`
- `clutter_penalty` / `clutter_score`
- `composite_score`
- `confidence`
- `warnings`, `notes`

Preprod writes candidate diagnostics to:

- `preprod/storefront/cover_thumbnail_candidates.json`

Review writes approved-cover diagnostics to:

- `review/storefront_optimization_report.json`

### Look Inside optimization

Scores the preview-priority opening window (cover-independent interior window based on first pages) and emits:

- per-page preview composite scores
- strongest/weakest preview pages
- warnings for low-hook/flat/text-heavy/low-contrast openings
- positive notes for strong conversion-facing pages

## Artifact

- `review/storefront_optimization_report.json`

Includes:

- `cover_thumbnail`
- `look_inside`
- `first_pages_strength_score`
- `summary_score`
- storefront warnings/notes/limitations

## Honesty / limitations

This packet is internal heuristic analysis only.

- No live competitor-cover data is used.
- No marketplace CTR/sales prediction is made.
- If text layer/OCR is unavailable, title readability is explicitly proxy-based (no fake OCR certainty).

## Deferred

- Live market/competitor benchmarking integrations.
- Learned conversion models.
- Any unbounded cover regeneration/search loop.
