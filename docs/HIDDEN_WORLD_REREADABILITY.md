# Hidden World / Re-readability (Packet 14)

Packet 14 adds a bounded hidden-world layer to improve rereadability and premium feel.

## Scope implemented

- Deterministic hidden-world planning from manuscript pages + Storyweaver illustration notes.
- Priority handling for manuscript `required_hidden_details`.
- Recurring motif, foreshadowing/callback, and parent-reward background detail planning.
- Prompt guidance/metadata attachment in studio prompt assembly.
- Page-level hidden-world adherence scoring in QC metadata.
- Sequence-level rereadability diagnostics in review artifacts.

## Feature flag

- `BOOKFORGE_HIDDEN_WORLD=true|false` (default true)
- Disabled mode is a safe no-op: no hidden-world planning artifact is required and scoring/guidance degrade safely.

## Artifacts

- `preprod/planning/hidden_world_plan.json`
- `review/hidden_world_report.json`
- `review/book_sequence_report.json` now includes `hidden_world_sequence`

## Honesty and limits

- This packet is metadata-first + heuristic scoring.
- It does **not** perform guaranteed object insertion/inpainting.
- It does **not** claim exact hidden-object detection success.
- QC reports explicitly note that hidden-detail adherence is heuristic.

## Deferred

- Provider-specific controlled insertion/inpainting workflows.
- Exact vision-model object verification guarantees.
- Global optimization loops for hidden-detail placement.
