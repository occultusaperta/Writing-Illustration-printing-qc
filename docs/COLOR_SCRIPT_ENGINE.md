# Color Script Engine (Packet 1)

This packet adds the **planning spine** for CSE only.

## Implemented now
- Typed data model (`EmotionType`, `EmotionColorProfile`, `HarmonyType`, `MasterPalette`, `PageColorSpec`, `TransitionSpec`, `PageEmotionAnalysis`).
- Centralized constants for hue ranges, emotion mapping, harmony, and target planning values.
- LAB utilities (LAB model, chroma, hue angle, temperature proxy, sRGB/LAB conversion, CIEDE2000).
- Deterministic per-page emotion analysis from page text.
- Deterministic master palette generation + validation.
- Per-page color script planning output with transition specs.
- Artifact emission in preprod planning stage:
  - `preprod/planning/emotion_analysis.json`
  - `preprod/planning/master_palette.json`
  - `preprod/planning/color_script.json`

## Feature flag
- `BOOKFORGE_COLOR_SCRIPT=true|false` (default true)

## Packet 2 integration (prompt coupling)
- CSE planning artifacts now flow into studio prompt assembly when present.
- Prompt contract objects now include `metadata.color_script_guidance` per page.
- Prompt text now receives explicit color direction (palette, mood descriptors, lighting/chroma/lightness targets, accent usage).
- Planning-derived negatives can append forbidden-palette avoidance guidance.
- If planning artifacts are missing, studio falls back safely to previous behavior.

## Deferred to later packets
- Color scoring/reselection loops.
- Postprocess tuning driven by color script.
- Transition repair/re-planning during generation.

## Color Script Engine Phase B — Image Scoring (Packet 3)

Packet 3 adds additive candidate image scoring only (no ranking/reselection changes yet).

### What is evaluated per candidate image
- CIELAB extraction and global color profile metrics:
  - measured lightness
  - measured chroma
  - measured temperature proxy
  - measured contrast
- Dominant color extraction via k-means (k=5), top-3 dominant LAB colors retained.
- Palette adherence scoring using ΔE2000 against allowed palette colors.
- Emotional target adherence scoring against per-page targets:
  - lightness/chroma/temperature/contrast
  - dominant color match
- Forbidden color contamination scoring using ΔE2000 against forbidden page colors.

### Composite score and disposition
- Composite score is weighted across all individual color metrics.
- Disposition labels are produced for future packets:
  - `ACCEPT`
  - `POST_PROCESS`
  - `REJECT`
- `post_process_actions` are suggestion hints only in this packet.

### Pipeline integration scope
- Color scores are attached to candidate metadata (`candidate.metadata.color_score`) during candidate QA scoring.
- Existing candidate ranking, reselection behavior, and post-processing logic are intentionally unchanged in Packet 3.

## Color Script Engine Phase C — Automatic Color Correction (Packet 4)

Packet 4 introduces controlled automatic post-processing driven by Packet 3 color scoring hints.

### What is applied
- Bounded, deterministic transforms selected from `post_process_actions` hints:
  - `lightness_shift` (LAB L-channel ±10 max)
  - `contrast_lift` (L curve factor up to 1.15)
  - `temperature_shift` (LAB a/b shift ±8 max)
  - `saturation_adjust` (chroma scaling up to 1.12 / down to 0.88)
  - `shadow_balance` (gamma in [0.9, 1.1])
- Transforms are applied in stable order and capped to at most 3 actions.

### Safety constraints
- No post-process is applied when `composite_score >= 0.92`.
- If corrected image rescoring yields a lower composite score, correction is aborted and original image is retained.

### Non-destructive pipeline behavior
- Runs during QC after scoring and before ranking.
- Original candidate remains unchanged and still participates in ranking.
- Corrected output is attached as metadata only:
  - `candidate.metadata.color_postprocess` (actions + score delta)
  - `candidate.metadata.corrected_variant` (path + postprocess score delta)

### Score delta tracking
- Corrected candidates are re-profiled and re-scored with `score_color_adherence`.
- Metadata records original score, corrected score, and `postprocess_score_delta` for deferred ranking work in later packets.
