# Monte Carlo Layout Exploration (Packet 17)

Packet 17 adds a **bounded local layout search** pass that evaluates multiple layout permutations per page/spread before final PDF rendering.

## Scope

- Explores bounded permutations of:
  - text zone placement and size
  - crop/art zone shift
  - architecture-variant swap within same architecture family
  - whitespace balance and gutter-safe positioning behavior
- Scores each permutation with deterministic, bounded metrics.
- Hard-rejects invalid permutations (fit/gutter/zone safety violations).
- Applies the selected permutation into the **existing** render path (`render_interior`) so output layout changes materially.

## What is optimized vs heuristic

### Explicitly optimized (bounded local objective)

- Composite score maximization among bounded candidates.
- Weighted objective includes:
  - text readability (`lum + texture/noise` proxy)
  - text fit capacity estimate
  - gutter safety
  - whitespace balance
  - architecture alignment
  - saliency-flow proxy terms
- Candidate dedupe prunes near-identical zone permutations before final selection.

### Still heuristic (intentional)

- Readability is image-stat proxy based (not OCR/reader model based).
- Text fit is capacity approximation (`chars` vs normalized zone area).
- Saliency terms use existing saliency-flow estimator.
- Architecture fit is geometric deviation from selected architecture variant.

## Bounded guarantees

- No global optimizer.
- No unbounded retry loops.
- Search cap per page/spread is fixed by config:
  - `max_permutations_per_page` (default `8`)
  - `max_permutations_per_spread` (default `12`)
- Deterministic seeded behavior via `layout_search_seed`.

## Feature flag

- `BOOKFORGE_MONTE_CARLO_LAYOUT=true|false` (default: `true`)
- Disabled behavior is safe no-op: architecture-applied layout path continues unchanged.

## Artifacts

- `review/layout_search_report.json`
  - permutations explored per page/spread
  - selected permutation id
  - top score
  - rejected count
  - explicit rejection reasons
  - weakest/strongest pages
  - sequence-level weak-layout notes
- `review/book_sequence_report.json`
  - additive `layout_search_summary` diagnostics

## Render metadata linkage

- Applied page architecture metadata includes:
  - selected permutation id and score
  - changed fields list
  - `text_zone` and `art_zone` deltas vs base architecture layout
- This makes final render output auditable against layout-search decisions.

## Packaging/verify

- `review/layout_search_report.json` is an expected package artifact.
- `verify` checks this report for required schema keys (`summary`, `pages`).

## Limitations (intentional)

- Local page/spread optimization only (not full-book global search).
- Heuristic scoring only; no learned layout scorer.
- Spread-local page-turn flow signal is lightweight and saliency-proxy based.

## Deferred

- Full-book Monte Carlo/global optimization.
- Iterative reselection-regeneration coupling with search-aware priors.
- Advanced compositor-level structure search (non-rectangular text, path text, complex panel graph optimization).
