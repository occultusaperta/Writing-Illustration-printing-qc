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

UI highlights:
- Black “Liquid Glass” local control plane.
- Full gate flow: doctor → preprod → approval gate → lock → studio → checkpoint gate → verify.
- Mandatory human gate editing via `APPROVAL.json` and `CHECKPOINT.json`.
- Max Quality toggle with MAX profile auto-select or fallback approval prefill.
- Built-in estimator for expected Fal calls.
- Run History, Publisher Checklist, Worst Pages overrides (`OVERRIDES.json`), and artifact open/download controls.

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
