# Packet 12 — Simulated Eye-Tracking / Saliency Flow

Packet 12 adds a bounded **simulated saliency-flow** layer for candidate QA and sequence review.

## What it implements

- Page-level saliency approximation from deterministic image heuristics:
  - grayscale local contrast
  - edge/detail density
  - mild center bias
- Per-candidate saliency flow scoring attached to QA metadata:
  - `primary_focus_score`
  - `text_quietness_score`
  - `page_turn_flow_score`
  - `spread_bridge_score`
  - `fixation_order_score`
  - `composite_score`
- Sequence-level saliency diagnostics integrated into:
  - `review/book_sequence_report.json` (`saliency_flow_sequence`)

## Artifact locations

- Candidate metadata:
  - `review/qa_report.json` → `attempts[*].best.metadata.saliency_flow_score`
- Sequence diagnostics:
  - `review/book_sequence_report.json` → `saliency_flow_sequence`

## Feature flag

- `BOOKFORGE_SALIENCY_FLOW=true|false` (default `true`)
- When disabled, candidate saliency metadata is omitted and all behavior remains safe no-op.

## Bounded behavior

- No unbounded search loops.
- No approval/lock/checkpoint gate changes.
- Existing ranking is preserved; saliency is only a weak tie-breaker.
- Reselection and targeted regeneration can use saliency metadata as an additive weak signal.

## Limitations / honesty note

This packet does **not** perform real human eye-tracking and makes no neuroscience or lab-validation claims.
It is a deterministic, heuristic approximation intended for auditable composition diagnostics only.
