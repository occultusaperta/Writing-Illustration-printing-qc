# Cinematic Camera System (Packet 11)

Packet 11 adds an additive camera-language layer so the book behaves more like a storyboard shot list.

## What this packet implements

- New bounded camera-language module suite in `bookforge/camera_language/`:
  - shot enums/types and typed planning/scoring outputs
  - bounded per-page shot planning
  - prompt guidance builders
  - lightweight shot-adherence candidate scoring
- Preprod planning artifact:
  - `preprod/planning/camera_sequence_plan.json`
- Prompt integration:
  - camera guidance lines are appended to existing planning prompt guidance
  - negative guidance lines for framing mismatches
  - prompt contract metadata now includes `metadata.camera_language_guidance`
- Candidate metadata integration:
  - `candidate.metadata.shot_adherence_score` is attached when shot planning exists
  - used only as a weak tie-breaker, not a ranking-system replacement
- Sequence review integration:
  - `review/book_sequence_report.json` now includes `camera_sequence` diagnostics
  - flags repetitive framing, weak progression, weak opening/climax/ending framing behavior

## Supported shot types

- `establishing_wide`
- `medium_interaction`
- `closeup_emotion`
- `extreme_closeup_detail`
- `birds_eye`
- `worms_eye`
- `over_shoulder`
- `dutch_tilt`

## Feature flag

- `BOOKFORGE_CAMERA_LANGUAGE=true|false` (default true)
- Safe no-op behavior when disabled or artifact/context missing.

## What this packet does NOT implement

- No VLM-grade camera understanding.
- No replacement of existing ranking/reselection/regeneration systems.
- No unbounded search loops.
- No compositor/PDF rewrite.

## Artifact locations

- `preprod/planning/camera_sequence_plan.json`
- `review/book_sequence_report.json` (extended with `camera_sequence` section)

## Scoring limitations

Shot adherence is heuristic and intentionally lightweight. It uses existing local image metrics (`focus_box`, focus overlap and simple framing/angle proxies) and provides bounded confidence/warnings for review/provenance.

## Deferred to later packets

- Model-based camera classification/VLM validation.
- Full sequence optimization that actively reranks/regenerates by global camera flow.
- Advanced spread-level shot continuity modeling.
