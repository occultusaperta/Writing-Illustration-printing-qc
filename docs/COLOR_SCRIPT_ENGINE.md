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
