# Packet 18: Bounded Book-Level Sequence Optimization

This module adds a deterministic, bounded whole-book optimization pass that swaps selected pages with existing runner-up candidates when sequence-level quality measurably improves.

## Feature flag

- `BOOKFORGE_SEQUENCE_OPTIMIZATION=true|false` (default: `false`)

## Bounded controls

- `BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_PAGES` (default: `10`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_MOVES` (default: `2`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_CANDIDATES_PER_PAGE` (default: `3`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_MIN_IMPROVEMENT` (default: `0.03`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_MAX_LOCAL_REGRESSION` (default: `0.015`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_OPENING_PROTECTION` (default: `1`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_CLIMAX_PROTECTION` (default: `1`)
- `BOOKFORGE_SEQUENCE_OPTIMIZER_ENDING_PROTECTION` (default: `1`)

## Objective components

Each candidate move computes explicit deltas for:

1. color flow
2. architecture flow
3. camera flow
4. saliency flow
5. typography rhythm (proxy via layout/focus safety)
6. hidden world continuity
7. storefront opening strength
8. character consistency
9. layout-search support
10. weak-cluster reduction

A weighted bounded composite delta is used to accept/reject moves. Local regressions above tolerance are rejected.

## Pipeline integration

The pass runs after targeted regeneration reporting and before final packaging. It:

- reads existing runner-up pools from QA attempts
- chooses bounded accepted moves
- applies accepted image swaps in-place (no regeneration)
- writes `review/sequence_optimization_report.json`
- threads summary into `review/production_report.json`

## Verification

`verify()` now checks `review/sequence_optimization_report.json` top-level fields. When missing, verify emits warning; when malformed, verify fails.
