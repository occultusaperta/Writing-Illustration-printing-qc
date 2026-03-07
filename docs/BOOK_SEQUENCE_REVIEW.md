# Book Sequence Review (Packet 8)

Packet 8 adds a **book-level sequence diagnostics layer** that reviews visual flow across the entire book and writes:

- `review/book_sequence_report.json`

This packet is reporting-only and does not alter approval/checkpoint behavior, ranking, or page reselection.

## What it analyzes

- **Color flow** from CSE planning + per-page QC metadata:
  - adjacent transition severity and smooth/abrupt alignment
  - repetitive runs
  - contamination cluster signals
  - reveal/climax contrast misses
- **Architecture flow** from PAS planning + applied architecture metadata:
  - variety score
  - repeated patterns
  - similar-energy clustering
  - pacing mismatches
  - text-heavy runs and relief gaps near resolution
- **Energy curve** comparison:
  - target PAS energy vs realized proxies from architecture + premium visual QC
  - flat stretches, jarring spikes, weak climax, unresolved energetic ending
- **Weak clusters**:
  - 2–4 page repetitive or weak stretches
  - clustered weak visual scores
  - transition-flat runs
  - clustered text-zone/gutter concerns

## Report structure

`review/book_sequence_report.json` contains:

- overall sequence summary + score
- `color_flow_summary_score`
- `architecture_flow_summary_score`
- `energy_curve_summary_score`
- transition-level findings with notes/warnings
- architecture flow section
- energy curve section
- weak cluster section
- per-page notes

## Safe no-op behavior

When planning artifacts or metadata are absent, generation is still safe:

- report still emits with limited diagnostics
- warnings explain missing inputs
- no hard gate changes are introduced

## Deferred to later packets

- automatic global candidate reselection
- Monte Carlo full-book optimization/search
- aggressive replacement/re-ranking rewrites
- typography or compositor rewrites
