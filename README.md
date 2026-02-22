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

## Preprod outputs
- Story parse + bible variants (`preprod/bible_variants/v1..vN`)
- Fal/Flux option images: character, style, cover concept
- Layout and typography option catalog + preview PDFs
- Single approval gate file: `preprod/APPROVAL.json`

## Lock + Studio guarantees
- `LOCK.json` freezes character/style/cover choices, prompt prefix, negative prompt, layout, typography, cover layout, print geometry, and Fal config.
- Studio refuses OpenAI images with exact error: `OpenAI image provider disabled; Fal/Flux only.`
- Studio renders premium interior + cover wrap + guides, runs strict preflight, and builds `bookforge_package.zip`.
