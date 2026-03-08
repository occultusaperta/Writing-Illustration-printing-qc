# Unified Book Quality Report

`review/book_quality_report.json` is the authoritative review artifact.

## Purpose

This report consolidates sequence, optimization, reselection, regeneration, and packet-level diagnostics into one migration-safe artifact.

## Schema (v1.0)

Top-level fields:

- `schema_version` (string)
- `generated_at` (ISO-8601 timestamp)
- `artifact` (`"book_quality_report.json"`)
- `summary_scores` (object)
  - `overall_sequence_score`
  - `color_flow_summary_score`
  - `architecture_flow_summary_score`
  - `energy_curve_summary_score`
  - optional packet summary scores when available (layout/storefront/character/dual/page-turn)
- `summary_notes` (string[])
- `warnings` (array of `{ source, message }`)
- `limitations` (array of `{ source, message }`)
- `per_page_notes` (array)
- `sequence_findings` (object)
- `actions_taken` (object)
  - `reselection`
  - `targeted_regeneration`
  - `sequence_optimization`
  - `layout_search`
- `legacy_artifacts` (object)
  - `deprecated`
  - `retained_for_compatibility`
  - `migration`

## Migration and compatibility

- Studio continues emitting legacy review artifacts for compatibility.
- Verify auto-generates `book_quality_report.json` from legacy artifacts when missing.
- Packaging expects `review/book_quality_report.json` as the canonical artifact.
- Legacy artifacts are treated as deprecated compatibility inputs.

## Availability / heuristics

Some sections are heuristic and may be absent or low-confidence when corresponding features are disabled. Disabled features are represented in `limitations`.


## Operator trust notes

- `review/book_quality_report.json` is the single review artifact operators should read first.
- Legacy review artifacts remain for compatibility/debug drill-down and can be missing fields without invalidating the authoritative report schema.
- If `verify` had to generate this report from legacy artifacts, treat the run as compatibility-mode and review `warnings` + `limitations` before using summary score deltas for decisions.
