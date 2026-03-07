# Page Architecture Sequencer (Packet 1)

This packet adds PAS planning modules and artifact output only.

## Implemented now
- Typed model for architecture planning (`ArchitectureType`, `ZoneType`, `Zone`, `ZoneConstraints`, `ArchitectureVariant`, `ArchitecturePlan`).
- Centralized print/physical constants (trim, bleed, safe/gutter, DPI, derived dimensions, normalized coordinates).
- Architecture families:
  - `FULL_BLEED_SPREAD`
  - `FULL_BLEED_SINGLE`
  - `VIGNETTE`
  - `SPOT_ILLUSTRATION`
  - `PANEL_SEQUENCE`
  - `WORDLESS_SPREAD`
  - `TEXT_DOMINANT`
  - `INSET_COMPOSITE`
- Representative template variants for each family.
- Deterministic energy curve generation from narrative functions.
- Bounded sequencing (beam search) with suitability matrix, hard constraints, and soft objective scoring.
- Artifact emission in preprod planning stage:
  - `preprod/planning/architecture_plan.json`
  - `preprod/planning/architecture_sequence_report.json`

## Feature flag
- `BOOKFORGE_PAGE_ARCHITECTURE=true|false` (default true)

## Packet 2 integration (prompt coupling)
- PAS planning artifacts now feed studio prompt assembly when present.
- Prompt contract objects now include `metadata.page_architecture_guidance` per page.
- Prompt text now receives architecture-aware composition hints (architecture type, camera/framing intent, spread/single mode, zone guidance, gutter safety).
- Planning-derived negatives can append text-zone/gutter/intent conflict avoidance hints.
- If planning artifacts are missing, studio falls back safely to previous behavior.

## Deferred to later packets
- Deep layout rewrite/rendering from PAS output.
- Advanced variant scoring and rescoring loops.
- Layout engine enforcement from PAS zones.
