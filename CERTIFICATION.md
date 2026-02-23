# Ultimate Imprint Certification

This checklist is the authoritative certification reference for a local/CLI Ultimate Imprint run.

## Golden path commands

Run all commands from repository root.

1. Environment doctor:
   - `python -m bookforge.cli doctor --strict`
2. Pre-production pack (creates `preprod/` and `APPROVAL.json`):
   - `python -m bookforge.cli preprod --story demo_story.md --out out --size 8.5x8.5 --pages 24`
3. Approval + lock (approval gate is mandatory):
   - Edit `out/preprod/APPROVAL.json` and set `approved: true` only after review.
   - `python -m bookforge.cli lock --out out --size 8.5x8.5 --pages 24`
4. Studio run from lock (local CLI only):
   - `python -m bookforge.cli studio --story demo_story.md --out out --size 8.5x8.5 --pages 24 --illustrator fal --require-lock`

## Required invariants

- Image provider policy is Fal/Flux only.
- OpenAI image generation must remain disabled with exact message:
  - `OpenAI image provider disabled; Fal/Flux only.`
- Approval gate remains mandatory:
  - Studio with `--require-lock` must require a valid `LOCK.json`.
  - Lock must require `approved: true` in `APPROVAL.json`.
- Workflow remains CLI/local only for certification.

## Quality gates

A certified run must meet all of the following:

- QA thresholds from lock profile (`LOCK.json -> qa`), including:
  - sharpness / entropy / contrast minimums
  - style similarity and drift bounds
  - text/watermark/logo likelihood limits
  - border artifact and composition overlap limits
- Visual integrity checks:
  - no unintended text/watermarks/logos
  - no severe border artifacts
- Composition checks:
  - safe focus placement, low bleed overlap risk
- Print QC checks:
  - brightness percentile bounds
  - out-of-gamut risk within threshold
  - preflight report status acceptable for print

## Proofing outputs and what to inspect

After `studio`, inspect the review bundle:

- `review/proof_pack.pdf`
  - Cover + interior consistency
  - QA fail summaries and suspicious pages
- `review/report.html`
  - QA table values by page
  - drift/regeneration/cache summaries
  - thumbnails and links to full assets
- `review/quality_summary.md`
  - worst pages by score
  - regenerated pages
  - integrity warnings
  - top drift pages and cache hit rate

Also verify `review/contact_sheet.pdf` and `review/thumbs/*` are present for quick visual audit.

## Release checklist (real book run)

- [ ] `doctor --strict` passes with `FAL_KEY` configured.
- [ ] `preprod` generated options and approval assets reviewed.
- [ ] `APPROVAL.json` explicitly approved by operator.
- [ ] `lock` generated and `LOCK.json` archived.
- [ ] `studio --require-lock --illustrator fal` completed.
- [ ] `preflight_report.json` reviewed and accepted.
- [ ] Proof artifacts reviewed (`proof_pack`, `report.html`, `quality_summary`).
- [ ] Package zip contains all release artifacts:
  - `interior.pdf`
  - `cover_wrap.pdf`
  - `cover_guides.pdf`
  - `preflight_report.json`
  - `LOCK.json`
  - `prompts.json`
  - `review/contact_sheet.pdf`
  - `review/qa_report.json`
  - `review/proof_pack.pdf`
  - `review/production_report.json`
  - `review/quality_summary.md`
  - `review/report.html`
  - `review/thumbs/*`
