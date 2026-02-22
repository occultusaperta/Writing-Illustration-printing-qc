# 1) What this repo is (in one paragraph)
This repository is a local-first children’s book production pipeline intended to turn an idea into production assets for Amazon KDP: story text, page planning, illustration prompts, generated illustrations (via Fal/Flux or OpenAI Images), interior PDF, cover-wrap PDF, and a preflight JSON report. README declares the intended flow as `IDEA/TEXT → STORY → PAGE PLAN → REAL IMAGE PROVIDER ... → KDP-oriented interior PDF + cover wrap PDF + preflight report`, while the actual orchestration is implemented in `bookforge/pipeline.py` by `BookforgePipeline.run(...)`, which writes `story.md`, `style_bible.json`, `page_plan.json`, `prompts.json`, image files, PDFs, and `preflight_report.json`.

Key evidence snippets:
- `README.md`: “`IDEA/TEXT → STORY → PAGE PLAN → REAL IMAGE PROVIDER ... → KDP-oriented interior PDF + cover wrap PDF + preflight report.`”
- `bookforge/pipeline.py`: `story = StoryAgent(writer=writer).run(...)` then writes story/style/page/prompt artifacts, generates images, renders PDFs, and runs preflight.

# 2) High-level architecture (modules and responsibilities)
Major active modules (current CLI path):

1. `bookforge/cli.py`
   - Defines CLI (`doctor`, `run`) and calls `BookforgePipeline`.
   - Evidence: `sub.add_parser("doctor"...)`, `sub.add_parser("run"...)`, `pipeline = BookforgePipeline()`.

2. `bookforge/pipeline.py`
   - Main orchestrator for doctor + full generation flow.
   - Picks writer, picks illustration provider, computes target image size, calls layout + preflight.
   - Evidence: imports `StoryAgent`, `FalFluxIllustrator`, `OpenAIImagesIllustrator`, `PDFLayoutEngine`, `KDPPreflight`.

3. `bookforge/story/`
   - Story generation layer with two writer modes:
     - `TemplateStoryWriter` in `bookforge/story/agent.py` (deterministic fallback).
     - `FullPipelineWriter` in `bookforge/story/full_pipeline_writer.py`, wrapping vendored `ChildrenStoryWriter`.
   - Evidence:
     - `if self.writer_name == "template": ... else: output = self.full_pipeline_writer.build_story(...)`
     - `from bookforge.story._vendor_fullpipeline import ChildrenStoryWriter`

4. `bookforge/illustration/`
   - Real illustration providers + placeholder generator:
     - `FalFluxIllustrator` (`bookforge/illustration/fal_flux.py`)
     - `OpenAIImagesIllustrator` (`bookforge/illustration/openai_images.py`)
     - `PlaceholderIllustrator` (`bookforge/illustration/fal_flux.py`)
   - Evidence: pipeline `_select_illustrator(...)` routes among these classes.

5. `bookforge/layout/pdf.py`
   - ReportLab PDF rendering engine for interior + cover wrap.
   - Uses trim + bleed math and draws image/text on each page.
   - Evidence: `PDFLayoutEngine.render(...)` and `parse_trim_size(...)`.

6. `bookforge/qc/kdp_preflight.py`
   - Static post-layout checks: page size, safe margin threshold, parity, embedded TTF detection, image min dimensions, cover existence.
   - Evidence: `checks.append({"check": "trim+bleed page size"...})`, `"embedded TrueType font present"`, `"image resolution >= 300DPI-equivalent"`.

7. `bookforge/knowledge/loader.py`
   - Loads required knowledge JSON and optional docs/PDF/style refs from repo-level `knowledge/` directory.
   - Evidence: `REQUIRED_JSON = ["directors.json", "visual_modes.json", "psychology.json"]` and roots set to `repo_root / "knowledge"`.

Also present (legacy/parallel path, likely older architecture):
- `bookforge/agents/*.py` + `bookforge/knowledge_loader.py` define a different agent-oriented pipeline with placeholder behavior and simplistic checks.
- These modules are not referenced by `bookforge/pipeline.py`.

# 3) Repo tree (curated)
```text
.
├── README.md
├── pyproject.toml
├── requirements.txt
├── setup.py
├── assets/
│   └── fonts/
│       └── NotoSans-Regular.ttf
├── knowledge/
│   ├── directors.json
│   ├── visual_modes.json
│   ├── psychology.json
│   ├── docs/
│   │   ├── writing_guide.md
│   │   └── design_notes.txt
│   ├── pdfs/
│   │   └── writing_principles.pdf
│   ├── style_refs/
│   │   └── .gitkeep
│   └── _imported/
│       ├── bookforge/...
│       └── full-pipeline/...
├── bookforge/
│   ├── __main__.py
│   ├── cli.py
│   ├── pipeline.py
│   ├── schemas.py
│   ├── illustration/
│   │   ├── fal_flux.py
│   │   └── openai_images.py
│   ├── layout/
│   │   └── pdf.py
│   ├── qc/
│   │   └── kdp_preflight.py
│   ├── story/
│   │   ├── agent.py
│   │   ├── full_pipeline_writer.py
│   │   ├── _vendor_fullpipeline/
│   │   │   ├── __init__.py
│   │   │   └── children_story_writer.py
│   │   └── _vendor_full_pipeline/
│   │       └── __init__.py
│   ├── knowledge/
│   │   ├── directors.json
│   │   ├── visual_modes.json
│   │   ├── psychology.json
│   │   └── loader.py
│   ├── agents/                     # legacy path (not used by active pipeline)
│   └── knowledge_loader.py         # legacy loader (not active CLI path)
├── examples/
│   └── demo.sh
└── demo.py
```

# 4) Entry points and how you’re supposed to run it
## A) Official entry points
1. Module execution
- File: `bookforge/__main__.py`
- Snippet:
  - `from bookforge.cli import main`
  - `if __name__ == "__main__": main()`
- Meaning: `python -m bookforge ...` enters `bookforge.cli:main`.

2. Console script entry
- File: `pyproject.toml`
- Snippet: `[project.scripts] bookforge = "bookforge.cli:main"`
- Meaning: installed CLI command `bookforge` maps to same main.

## B) CLI definition and commands
- Defined in: `bookforge/cli.py`.
- Commands:
  1) `doctor [--strict]`
     - Calls `pipeline.doctor(strict=args.strict)`.
     - Exits `0` on PASS, `1` otherwise.
  2) `run --idea ... --out ... [--pages ... --size ... --stop-after style --writer ... --illustrator ... --allow-placeholder]`
     - Calls `pipeline.run(...)`.
     - Exits `0` when returned status is `PASS|WARN|STOPPED_AFTER_STYLE`.

## C) Expected outputs
Based on `README.md` and `bookforge/pipeline.py`, expected files include:
- `style_bible.json`
- `story.md`
- `story_metadata.json`
- `page_plan.json`
- `prompts.json`
- `images/page_001.png ...`
- `interior.pdf`
- `cover_wrap.pdf`
- `preflight_report.json`

## D) Non-aligned/legacy entrypoint
- `demo.py` imports `from bookforge.pipeline import Pipeline`.
- In current code, class is `BookforgePipeline`, not `Pipeline`.
- Therefore this script appears stale/broken relative to active architecture.

# 5) Pipeline walkthrough (code-level)
## 1. Story generation
- Orchestration: `BookforgePipeline.run(...)` in `bookforge/pipeline.py`
  - `story = StoryAgent(writer=writer).run(idea=idea, pages=pages)`
- Dispatcher: `StoryAgent` in `bookforge/story/agent.py`
  - Chooses:
    - `TemplateStoryWriter.build_story(...)` (template mode)
    - `FullPipelineWriter.build_story(...)` (default full-pipeline mode)
- Full-pipeline writer wrapper: `bookforge/story/full_pipeline_writer.py`
  - Uses vendored class: `ChildrenStoryWriter` from `bookforge/story/_vendor_fullpipeline/children_story_writer.py`
  - Calls `self.writer.generate(...)` with `knowledge`, `writing_docs_text`, `design_docs_text`.

Import existence verification:
- `from bookforge.story._vendor_fullpipeline import ChildrenStoryWriter` → EXISTS:
  - `bookforge/story/_vendor_fullpipeline/__init__.py`
  - `bookforge/story/_vendor_fullpipeline/children_story_writer.py`

## 2. Page plan
- File: `bookforge/pipeline.py`
- Logic:
  - Builds `page_plan = {"pages": [...], ...}` from `story["pages"]`
  - Adds `spread = (page_number + 1) // 2`
  - Writes `page_plan.json`.

## 3. Prompt generation
- File: `bookforge/pipeline.py`
- Logic:
  - Builds prompt strings:
    - `"children's book illustration, {director} inspired, {visual_mode}, {scene_description}"`
  - Writes `prompts.json`.

## 4. Illustration providers (Fal / OpenAI / Placeholder)
- Selection:
  - Function `_select_illustrator(...)` in `bookforge/pipeline.py`.
  - Priority for `auto`: Fal if `FAL_KEY`, else OpenAI if `OPENAI_API_KEY`, else placeholder only with `--allow-placeholder`.

- Fal provider:
  - `bookforge/illustration/fal_flux.py`, class `FalFluxIllustrator`.
  - API endpoint: `https://fal.run/fal-ai/flux/schnell`.
  - Payload includes explicit width/height from pipeline `image_size_px`.

- OpenAI provider:
  - `bookforge/illustration/openai_images.py`, class `OpenAIImagesIllustrator`.
  - API endpoint: `https://api.openai.com/v1/images/generations`.
  - Payload hard-codes size: `"size": "1024x1024"` (ignores requested `image_size_px`).

- Placeholder provider:
  - `PlaceholderIllustrator` in `bookforge/illustration/fal_flux.py`.
  - Generates local PNG placeholders via PIL.

## 5. PDF layout engine
- File: `bookforge/layout/pdf.py`, class `PDFLayoutEngine`.
- Key flow:
  - `trim_w, trim_h = parse_trim_size(size)`
  - `bleed = 0.125`, `safe_margin = 0.375`
  - Page size = `(trim + 2*bleed) * 72` points.
  - Draws image inside safe-area inset (`drawImage(... preserveAspectRatio=True, anchor="c")`).
  - Draws truncated text line (`page["text"][:130]`).
  - Cover wrap is a simple frame with text labels.

## 6. KDP preflight QC
- File: `bookforge/qc/kdp_preflight.py`, class `KDPPreflight`.
- Checks include:
  - Interior page MediaBox matches trim+bleed expected size.
  - Safe margin threshold check (`>= 0.375in`).
  - Even page parity warning.
  - Embedded TrueType font presence by scanning PDF font descriptors.
  - Image dimension min check for “300DPI-equivalent”.
  - Cover wrap file existence and non-empty size.

# 6) Current state: DONE vs NOT DONE (brutally honest)
| Component | Status (DONE / PARTIAL / MISSING / PLACEHOLDER) | Evidence (file path + snippet) | Why it matters |
|---|---|---|---|
| Story writer (template vs full-pipeline) | PARTIAL | `bookforge/story/agent.py`: `if self.writer_name == "template" ... else ... full_pipeline_writer`; full pipeline delegates to vendored deterministic generator in `children_story_writer.py` (no model/API call). | There is a two-mode architecture, but “full-pipeline” is still a thin wrapper around local templated logic, limiting story originality/depth. |
| Missing/required files referenced by imports | PARTIAL | Active imports mostly exist. Example exists: `bookforge/story/full_pipeline_writer.py` imports `_vendor_fullpipeline` and files exist. But stale mismatch exists: `demo.py` imports `Pipeline` while `bookforge/pipeline.py` defines `BookforgePipeline`. Also duplicate vendor dir `_vendor_full_pipeline/` only has docstring init. | Import mismatches indicate dead/stale code and integration confusion. |
| OpenAI images sizing correctness for print | MISSING | `bookforge/illustration/openai_images.py`: payload hard-coded `"size": "1024x1024"`; `generate(... image_size_px)` never uses `image_size_px`. | For print sizes requiring larger/non-square rasters, this can fail 300-DPI-equivalent requirements and damage quality/cropping. |
| Fal provider sizing correctness | PARTIAL | `bookforge/illustration/fal_flux.py` passes requested `width/height` in payload. But no clamp/validation against provider-supported size/aspect constraints. | Better than OpenAI path, but still fragile if target dimensions exceed/violate provider limits or need intelligent scaling. |
| Layout engine interior quality | PARTIAL | `bookforge/layout/pdf.py`: text uses single `drawString(...)` with `page["text"][:130]`; no paragraph layout/hyphenation/leading controls; image placed in reduced safe box with fixed `+56` offset. | Not premium typography or art-direction quality; risks awkward text fit and underutilized page composition. |
| Layout engine cover wrap quality | PLACEHOLDER | `bookforge/layout/pdf.py`: cover draws “BookForge Cover Wrap”, “Front + Back + spine area”, and a simple rectangle; width uses fixed `+0.25` spine estimate. | Premium KDP cover requires exact spine math based on page count/paper type and barcode/safe area handling; current output is not production-grade. |
| Preflight rigor | PARTIAL | `bookforge/qc/kdp_preflight.py` does baseline checks (size, parity, font embedding signal, min image dimensions, cover existence), but no deep PDF profile checks, bleed object checks, color space checks, or cover geometry validation. | Good baseline gate, insufficient for “highest printing standards”. |
| Fonts embedding behavior | PARTIAL | `bookforge/layout/pdf.py`: registers TTF if `assets/fonts/NotoSans-Regular.ttf` exists; otherwise falls back to Times-Roman. `kdp_preflight.py` checks for `/FontFile2` presence. | Embedding is attempted but not guaranteed across all text/font paths; fallback may weaken consistency and premium typography. |

# 7) “Premium print” gap list (static analysis only)
## 1) Image resolution pipeline (300DPI equivalent for trim+bleed)
- Currently implemented:
  - Pipeline computes target pixels from trim+bleed at 300 DPI (`bookforge/pipeline.py`: `px_size = (int((trim_w + 0.25) * 300), int((trim_h + 0.25) * 300))`).
  - Preflight checks minimum image dimensions (`bookforge/qc/kdp_preflight.py`).
- Missing:
  - OpenAI path ignores computed target and always requests 1024x1024.
  - No upscaling/downscaling policy or quality guardrails.
- Files involved:
  - `bookforge/pipeline.py`
  - `bookforge/illustration/openai_images.py`
  - `bookforge/qc/kdp_preflight.py`

## 2) Aspect ratio handling & cropping
- Currently implemented:
  - `drawImage(... preserveAspectRatio=True, anchor="c")` in layout.
- Missing:
  - No explicit crop strategy (cover fit, smart focal point, letterboxing rules, trim-safe subject placement).
  - No per-page composition metadata from prompt/story stage to protect key subjects near trim.
- Files involved:
  - `bookforge/layout/pdf.py`
  - `bookforge/pipeline.py`

## 3) Text typography (wrapping, hyphenation, spacing, size)
- Currently implemented:
  - Fixed font size 12; one-line draw; hard truncation `[:130]`.
- Missing:
  - Paragraph engine, width-aware wrapping, hyphenation, leading/grid system, orphan/widow control, dynamic font sizing, style hierarchy.
- Files involved:
  - `bookforge/layout/pdf.py`

## 4) Full-bleed placement correctness
- Currently implemented:
  - Page size includes bleed, but images are drawn inside safe-area frame (not true full bleed).
- Missing:
  - Intentional full-bleed art extension to page edges where needed.
  - Separate template logic for text-over-image vs text-only pages.
- Files involved:
  - `bookforge/layout/pdf.py`

## 5) Cover wrap math (spine width, barcode safe area, guides)
- Currently implemented:
  - Cover width formula uses fixed `+0.25` center component; simple visual placeholder.
- Missing:
  - Spine width formula based on final page count and paper stock.
  - Front/back panels, spine text alignment rules, barcode exclusion zone, guide layers, bleed/safe overlays.
- Files involved:
  - `bookforge/layout/pdf.py`
  - `bookforge/pipeline.py` (doesn’t pass page-count-dependent cover specs)

## 6) PDF technical quality (font embedding, compression choices)
- Currently implemented:
  - Optional TTF registration from assets font.
  - Preflight checks for an embedded TrueType font indicator.
- Missing:
  - PDF/X-like constraints, color management strategy, controlled compression and image sampling, metadata completeness.
  - `pageCompression=0` is explicitly used for interior and cover; no production optimization path.
- Files involved:
  - `bookforge/layout/pdf.py`
  - `bookforge/qc/kdp_preflight.py`

# 8) What we should remove later to make it “private & light”
(Recommendation only; no code changes performed.)

1. Remove stale/duplicate architecture paths if not used:
   - `bookforge/agents/*`, `bookforge/knowledge_loader.py`, `demo.py`, duplicate vendor folder `bookforge/story/_vendor_full_pipeline/`.
   - Rationale: active path is `bookforge/pipeline.py` + `story/illustration/layout/qc`; extras increase maintenance and confusion.

2. Trim repository ballast in `knowledge/_imported/` if not needed at runtime.
   - Rationale: looks archival/reference-oriented rather than required for execution.

3. Keep only essential knowledge assets used by loader:
   - Required JSON + concise docs and style refs actually consumed by `bookforge/knowledge/loader.py`.

4. No auth/billing/web/server components detected in inspected files.
   - Good for private internal tool footprint.

# 9) Minimal next steps (no code yet)
Top 10 changes to reach A) reliable KDP-ready and B) premium “creme de la creme” output:

1. Make OpenAI image requests respect target print dimensions (or nearest validated size policy).
   - Files: `bookforge/illustration/openai_images.py`, `bookforge/pipeline.py`.

2. Add provider capability layer with size/aspect negotiation and deterministic fallback.
   - Files: `bookforge/pipeline.py`, `bookforge/illustration/fal_flux.py`, `bookforge/illustration/openai_images.py`.

3. Replace single-line truncated text rendering with paragraph composition engine.
   - Files: `bookforge/layout/pdf.py`.

4. Implement page templates (full-bleed, vignette, text panel, spread-aware variants) driven by page metadata.
   - Files: `bookforge/layout/pdf.py`, `bookforge/pipeline.py`.

5. Add explicit crop/fit strategies with safe subject region support.
   - Files: `bookforge/layout/pdf.py`, optionally `bookforge/pipeline.py` prompt/page metadata.

6. Implement accurate KDP cover-wrap generator using computed spine width from interior page count + paper profile.
   - Files: `bookforge/layout/pdf.py`, `bookforge/pipeline.py`.

7. Upgrade preflight to validate cover geometry, bleed content, color-space assumptions, and stronger font embedding checks.
   - Files: `bookforge/qc/kdp_preflight.py`.

8. Add robust font management: family selection, fallback list, embed verification per page, and typography style tokens.
   - Files: `bookforge/layout/pdf.py`, `assets/fonts/`.

9. Unify codebase by removing or isolating legacy pipeline paths and fixing stale entrypoints (`demo.py`).
   - Files: `demo.py`, `bookforge/agents/*`, `bookforge/knowledge_loader.py`, possibly packaging metadata.

10. Increase story/illustration direction fidelity: richer style bible and page-level art direction constraints.
   - Files: `bookforge/pipeline.py`, `bookforge/story/agent.py`, `bookforge/story/full_pipeline_writer.py`, `bookforge/story/_vendor_fullpipeline/children_story_writer.py`, `knowledge/docs/*`.
