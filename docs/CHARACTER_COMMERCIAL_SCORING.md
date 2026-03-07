# Character Commercial Scoring (Packet 16)

Packet 16 adds a bounded additive layer for **baby-schema calibration** and **character toyetic scoring**.

## Scope

This packet introduces:

- proxy-based baby-schema scoring (cuteness/readability signal)
- toyetic scoring (signature feature strength, plush friendliness, small-scale readability)
- silhouette extraction/scoring proxies
- page-level QA metadata attachment
- review artifact generation:
  - `review/character_commercial_report.json`
- sequence report threading via `character_commercial_summary`

This packet is additive and **does not** replace ranking, lock, approval, checkpoint, preflight, or print constraints.

## Feature flag

- `BOOKFORGE_CHARACTER_COMMERCIAL_SCORING=true|false` (default `true`)

Behavior:

- enabled: scoring metadata is attached and review artifact is generated
- disabled: safe no-op report is generated with `enabled=false`

## Metadata attachments in candidate QA

When enabled, each candidate metadata may include:

- `metadata.baby_schema_score`
- `metadata.toyetic_score`
- `metadata.silhouette_score`
- `metadata.character_commercial_score`

The signal is used as a weak additive ranking tie-break term only.

## Review artifacts

- `review/character_commercial_report.json`
  - lead character strength summary
  - strongest / weakest pages
  - consistency notes
  - warnings (generic/weak toyetic/weak baby-schema/weak silhouette)
  - positive notes
  - limitations

- `review/book_sequence_report.json`
  - includes `character_commercial_summary` section when available

## Limitations

- Uses bounded image heuristics and proxies only.
- Does **not** claim biometric/anthropometric certainty.
- Does **not** guarantee manufacturing outcomes (plush/toy/sales/CTR).
- Does **not** run unbounded optimization or regeneration loops.

## Deferred work

- landmark-aware face/body parsing if introduced by a future packet
- multi-angle persistent identity embeddings
- real manufacturing feasibility models
- market/retail conversion modeling
