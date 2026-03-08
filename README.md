# BookForge CLI (Fal/Flux-only, lock-gated)

## Requirements
- Python 3.9+
- `FAL_KEY` is required for any image generation (`preprod`, `studio`).
- `OPENAI_API_KEY` is optional and used for **text-only** story cue extraction.

## Golden Path
```bash
bookforge doctor --strict
bookforge preprod --story examples/sample_story.md --out dist/run --size 8.5x8.5 --pages 24 --variants 4
# edit dist/run/preprod/APPROVAL.json and set approved=true
bookforge lock --out dist/run --size 8.5x8.5 --pages 24
bookforge studio --story examples/sample_story.md --out dist/run --size 8.5x8.5 --pages 24 --illustrator fal --require-lock
```

## UI Quickstart
```bash
pip install -e ".[ui]"
bookforge ui
```

## RunPod B200 runtime quickstart

```bash
export BOOKFORGE_RUNTIME_PROVIDER=runpod
export RUNPOD_API_KEY=...
bookforge runtime-provision
bookforge runtime-bootstrap
bookforge runtime-launch
bookforge runtime-health --url http://<runtime-host>:8188/health
```

Then point image generation to flux local:

```bash
export BOOKFORGE_IMAGE_PROVIDER=flux_local
export BOOKFORGE_FLUX_LOCAL_URL=http://<runtime-host>:8188/generate
```

UI highlights:
- Black “Liquid Glass” local control plane.
- Full gate flow: doctor → preprod → approval gate → lock → studio → checkpoint gate → verify.
- Mandatory human gate editing via `APPROVAL.json` and `CHECKPOINT.json`.
- Max Quality toggle with MAX profile auto-select or fallback approval prefill.
- Built-in estimator for expected Fal calls.
- Run History, Publisher Checklist, Worst Pages overrides (`OVERRIDES.json`), and artifact open/download controls.


## Operator trust order (diagnosing a run)

When diagnosing output quality or deciding whether a run is trustworthy, check artifacts in this order:

1. `preflight_report.json` — hard print gate pass/fail.
2. `review/qa_report.json` + `review/visual_critic_report.json` — per-page QC outcomes.
3. `review/book_quality_report.json` — **authoritative unified review artifact**.
4. `review/production_report.json` — provenance (provider, endpoint, feature flags, runtime metadata).
5. Legacy review JSON files — compatibility inputs only, not the primary source of truth.

If `verify` says it had to generate `review/book_quality_report.json` from legacy artifacts, treat that run as compatibility-mode: inspect `summary_notes`, `warnings`, and `limitations` before using the summary scores for decisions.

## Feature flags (operator-impacting)

Defaults are conservative and deterministic:

- Enabled by default: `BOOKFORGE_COLOR_SCRIPT`, `BOOKFORGE_PAGE_ARCHITECTURE`, `BOOKFORGE_CAMERA_LANGUAGE`, `BOOKFORGE_HIDDEN_WORLD`, `BOOKFORGE_DYNAMIC_TYPOGRAPHY`, `BOOKFORGE_MONTE_CARLO_LAYOUT`, `BOOKFORGE_STOREFRONT_OPTIMIZATION`, `BOOKFORGE_CHARACTER_COMMERCIAL_SCORING`, `BOOKFORGE_DUAL_AUDIENCE`, `BOOKFORGE_PAGE_TURN_TENSION`.
- Disabled by default: `BOOKFORGE_RESELECTION`, `BOOKFORGE_TARGETED_REGENERATION`.

`review/production_report.json` now records the resolved feature-flag snapshot used during studio.

## Preprod outputs
- Story parse + bible variants (`preprod/bible_variants/v1..vN`)
- Fal/Flux option images: character, style, cover concept
- Layout and typography option catalog + preview PDFs
- Single approval gate file: `preprod/APPROVAL.json` (includes `fal_endpoint`, defaulting to `https://fal.run/fal-ai/flux/schnell`).

## Lock + Studio guarantees
- `LOCK.json` freezes character/style/cover choices, prompt prefix, negative prompt, layout, typography, cover layout, print geometry, and Fal config. You can switch `fal_endpoint` in approval to a higher-quality Fal endpoint (if available in your account) before locking.
- Studio refuses OpenAI images with exact error: `OpenAI image provider disabled; Fal/Flux only.`
- Studio renders premium interior + cover wrap + guides, runs strict preflight, and builds `bookforge_package.zip`.

## Ultimate Imprint profile defaults
- `crop_mode`: `smart` (fallback `center`) to preserve subject focus when final trim crop is applied.
- Director Grade controls (all deterministic with lock seed):
  - `director_grade_enabled: true`
  - `tone_curve_preset: storybook_lux` (`neutral`, `cinematic_soft`, `watercolor_warm`)
  - `tone_curve_strength: 0.35`
  - `paper_texture_strength: 0.08`
  - `paper_texture_scale: 1.0`
  - `global_grade_strength: 0.30`
- Print QC thresholds in approval/lock QA profile:
  - `min_brightness_p05: 15`
  - `max_brightness_p95: 245`
  - `max_out_of_gamut_risk: 0.35`
  - `max_book_palette_drift: 0.45`
- Cover title placement supports `title_placement: auto` to pick top/middle/bottom by lowest edge busyness in front safe area.
- Studio now always emits `review/report.html` and `review/thumbs/*` for static local proofing.
