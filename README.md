# BookForge v2 Pipeline (No Stubs by Default)

End-to-end local pipeline:

IDEA/TEXT → STORY → PAGE PLAN → REAL IMAGE PROVIDER (Fal/Flux or OpenAI Images) → KDP-oriented interior PDF + cover wrap PDF + preflight report.

## Commands

```bash
python -m bookforge doctor
python -m bookforge doctor --strict
python -m bookforge run --idea "a brave little kite" --pages 24 --size 8.5x8.5 --out dist/run1
python -m bookforge run --idea "a brave little kite" --pages 24 --size 8.5x8.5 --out dist/style --stop-after style
```

## How to run

```bash
export FAL_KEY=...  # preferred
# OR
export OPENAI_API_KEY=...

python -m bookforge run --idea "a brave little kite" --pages 24 --size 8.5x8.5 --out dist/run1
```

Use placeholders only when explicitly requested:

```bash
python -m bookforge run --idea "a brave little kite" --pages 24 --out dist/placeholder --illustrator placeholder --allow-placeholder
```

## Output files

- `style_bible.json`
- `story.md`
- `story_metadata.json`
- `page_plan.json`
- `prompts.json`
- `images/page_001.png ...`
- `interior.pdf`
- `cover_wrap.pdf`
- `preflight_report.json`

All JSON artifacts include provenance keys:
`knowledge_sources`, `knowledge_keys_used`, `knowledge_docs_used`, `pdf_sources_used`, `style_refs_used`.
