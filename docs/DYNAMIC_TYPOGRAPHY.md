# Dynamic Typography System (Packet 13)

Packet 13 adds a bounded, deterministic typography planning/scoring/rendering layer for expressive vector text overlays.

## Scope

- Storyweaver-aware typography intent extraction (headings/emphasis/all-caps/pause spacing/tiny trailing words).
- Deterministic `PageTypographyPlan` generation per page.
- Typography readability scoring metadata.
- PDF vector overlay consumption of typography plans (no raster text baking).
- Sequence-level typography diagnostics in review artifacts.

## Guarantees

- **Exact printed text is preserved** (no paraphrasing, no line deletion, no story rewrite).
- **Vector-only text overlays** remain in `interior.pdf`.
- Existing overflow hard-fail behavior is preserved.
- If planning metadata is absent or invalid, renderer safely falls back to legacy directive overlays.

## Feature flag

- `BOOKFORGE_DYNAMIC_TYPOGRAPHY=true|false` (default: true)
- Disabled flag behavior: safe no-op (legacy behavior preserved).

## Artifacts

- `review/book_sequence_report.json` now includes `typography_sequence`.
- `review/typography_report.json` mirrors typography sequence diagnostics.

## Deferred work

- Font family/kerning design-space search.
- Script- and language-specific typography shaping.
- Rich curved text path layout or freeform compositor redesign.
- Learned typography ranking models (Packet 13 remains rule-based).
