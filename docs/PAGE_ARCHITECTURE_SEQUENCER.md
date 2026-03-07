# Page Architecture Sequencer (Packets 1, 2, 6)

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

## Packet 6 integration (local variant scoring)
- New `bookforge.page_architecture.scoring` module computes bounded local architecture scores against generated candidates.
- Scored dimensions per candidate:
  - text readability in planned text/caption zones (busyness + local detail + contrast potential)
  - focal alignment (saliency peak landing in art vs text zones)
  - text fitting estimate (text demand vs declared text-zone area, age-band aware)
  - gutter safety for spread-capable layouts (seam detail density, focal-in-gutter, seam overlap, face-like signal)
- Typed result model: `ArchitectureVariantScoreResult` with component scores, composite score, and diagnostics/notes.
- Studio pipeline now loads planning architecture variants when present and passes page text + age band into candidate QA scoring.
- Candidate metadata now includes `metadata.page_architecture_score` per variant when architecture planning artifacts are available.
- Review/provenance impact: architecture score diagnostics ride along in existing QA attempt metadata and are human-inspectable in review artifacts.
- Ranking impact is intentionally weak: architecture score is metadata-first and only used as a late tie-break term.

## Deferred to later packets
- Deep layout rewrite/rendering from PAS output.
- Advanced rescoring loops across the full book / global architecture reselection.
- Layout engine enforcement from PAS zones.
- Monte Carlo multi-pass optimization and compositor rewrites.
