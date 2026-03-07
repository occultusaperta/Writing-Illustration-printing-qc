# Page Architecture Sequencer (Packets 1, 2, 6, 7)

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



## Packet 7 integration (layout/compositor enforcement)
- New layout application module: `bookforge.page_architecture.layout_apply`.
- PAS plan + selected variant now translate into concrete per-page layout instructions used by the existing PDF renderer path.
- Enforced architecture behavior now includes:
  - `FULL_BLEED_SPREAD`: full-page art, spread-mode hints, gutter-sensitive metadata.
  - `FULL_BLEED_SINGLE`: side-aware behavior (art-dominant page vs facing text-priority page).
  - `VIGNETTE`: bounded non-bleed illustration placement with reserved whitespace.
  - `SPOT_ILLUSTRATION`: reduced art footprint with surrounding whitespace preserved.
  - `PANEL_SEQUENCE`: practical bounded multi-panel arrangement and caption/text zone.
  - `WORDLESS_SPREAD`: body-text suppression in rendering.
  - `TEXT_DOMINANT`: text-zone priority with secondary art placement.
  - `INSET_COMPOSITE`: base art with inset overlays and simple border treatment.
- PAS-selected text zones are applied at layout time while existing typography overflow hard-fail remains in force.
- If PAS text zone cannot fit text, renderer falls back to preset-safe panel region and records fallback metadata.
- Gutter/safe enforcement is applied for spread-sensitive architectures through layout-time placement adjustments/flags.
- Pipeline review output now includes `review/applied_page_architecture.json` for per-page human verification.
- `render_interior` now returns `applied_page_architecture` metadata rows to surface architecture application status.

## Deferred to later packets
- Deep layout rewrite/rendering from PAS output.
- Advanced rescoring loops across the full book / global architecture reselection.
- Monte Carlo multi-pass optimization and compositor rewrites.
