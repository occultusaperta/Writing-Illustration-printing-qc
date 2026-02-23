# BookForge Local UI

BookForge includes an optional local-only Streamlit interface that controls the existing pipeline:

`doctor → preprod → approval gate → lock → studio → checkpoint gate → verify`

## Install

```bash
pip install -e '.[ui]'
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

## What the UI does

- Uses existing CLI commands via subprocess for safety and compatibility.
- Preserves manual gates (`APPROVAL.json` and `CHECKPOINT.json`) and pauses for human action.
- Keeps Fal/Flux-only image behavior and existing quality logic untouched.
- Offers best-effort "Open in system viewer" buttons for local artifacts.
