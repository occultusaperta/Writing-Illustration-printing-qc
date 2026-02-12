# BookForge v1 Pipeline

End-to-end local pipeline:

IDEA/TEXT → STORY → PAGE PLAN → (optional) Fal/Flux provider → KDP-oriented interior PDF + cover wrap PDF + preflight report.

## Commands

```bash
python -m bookforge doctor
python -m bookforge run --idea "a brave little kite" --pages 24 --size 8.5x8.5 --out dist/run1
python -m bookforge run --idea "a brave little kite" --pages 24 --size 8.5x8.5 --out dist/style --stop-after style
```

## Output files

- `style_bible.json`
- `story.md`
- `page_plan.json`
- `prompts.json`
- `images/page_001.png ...`
- `interior.pdf`
- `cover_wrap.pdf`
- `preflight_report.json`

## Knowledge import notes

Knowledge files are loaded from repository root:

- `knowledge/directors.json`
- `knowledge/visual_modes.json`
- `knowledge/psychology.json`
- `knowledge/pdfs/*.pdf` (if present)

Original imported source snapshots are preserved under `knowledge/_imported/`.

## Fal/Flux behavior

- If `FAL_KEY` is unset: pipeline does **not** fail and generates high-resolution placeholder images via Pillow.
- If `FAL_KEY` is set: current v1 still uses deterministic local placeholders but marks provider mode accordingly.

## KDP preflight checks (v1)

- Trim + bleed page size check
- Safe margin check
- Fonts present in PDF resources
- Placed image dimensions meet 300-DPI-equivalent target
- Page count parity (warning if odd)
- Cover wrap exists
