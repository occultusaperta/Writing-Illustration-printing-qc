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

## Deferred to later packets
- Prompt coupling to CSE.
- Color scoring/reselection loops.
- Postprocess tuning driven by color script.
- Transition repair/re-planning during generation.
