# BookForge Local UI

BookForge includes an optional local-only Streamlit interface that controls the existing pipeline:

`doctor → preprod → approval gate → lock → studio → checkpoint gate → verify`

## Install

```bash
pip install -e ".[ui]"
```

## Run

```bash
bookforge ui
# or
./scripts/ui.sh
```

Optional host/port:

```bash
bookforge ui --host 127.0.0.1 --port 8501
```

## Control-plane features

- **Black Liquid Glass theme** for dark, high-contrast operation.
- **Fal/Flux-only enforcement** with explicit message: `OpenAI image provider disabled; Fal/Flux only.`
- **Max Quality (slower)** toggle:
  - Auto-selects `ultimate_imprint_8p5x8p5_image_heavy_MAX` when available.
  - Falls back to approval prefill defaults when MAX profile is unavailable.
- **Estimator** panel (before Studio run) for low/likely/high Fal-call ranges.
- **Run History** scan from `dist/*` with preflight status + quick artifact open buttons.
- **Worst Pages + overrides** editor that writes `OVERRIDES.json` and supports rerunning Studio.
- **Checkpoint UI** for structured JSON overrides (`page_prompt_addendum`, `force_regen`, `variant_preference`) and approve/continue action.
- **Verify + Outputs** with open folder, open artifact buttons, and package download.
- **Publisher Checklist** panel with `CERTIFICATION.md` viewer and UI-only release checklist.

## Design constraints preserved

- CLI commands and quality logic are unchanged; UI drives existing commands via subprocess.
- Approval and checkpoint gates remain mandatory.
- Local-only operation (no auth/billing services).
- Fal key remains env-only (`FAL_KEY`/`Fal_key`/`fal_key`) and is never printed by the UI.
