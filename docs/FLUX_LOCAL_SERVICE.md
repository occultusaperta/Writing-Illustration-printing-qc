# Local Flux Service Contract

BookForge supports a practical local Flux HTTP contract used by the `flux_local` provider.

## Endpoints

- `GET /health` → status, service info, runtime mode, model.
- `POST /generate` request fields:
  - required: `prompt`, `width`, `height`
  - optional: `negative_prompt`, `steps`, `seed`, `guidance`
  - optional: `quality_preset`: `draft|premium|ultimate`
  - optional: `references` (list of base64 PNG strings or file paths before provider encoding)
  - optional: `lora_slots`, `spread`, `variant_count`, `model_name`
- `POST /batch` with `{ "requests": [ ...generate payloads... ] }`

## Response schema

`/generate` returns:

- `image_b64`
- `image_path`
- `seed`
- `provider`
- `model`
- `elapsed_ms`
- `cache_key`
- `provenance` object (`runtime_mode`, `references`, `variant_count`)

## Running the service

```bash
python -m bookforge.illustration.providers.flux_local_service --host 0.0.0.0 --port 8188
```

Use environment variables:

```bash
export BOOKFORGE_IMAGE_PROVIDER=flux_local
export BOOKFORGE_FLUX_LOCAL_URL=http://127.0.0.1:8188/generate
export BOOKFORGE_FLUX_RUNTIME_MODE=fallback   # or diffusers on a real GPU host
export BOOKFORGE_FLUX_MODEL=black-forest-labs/FLUX.1-schnell
```

## Runtime mode behavior

- `fallback`: deterministic placeholder rendering with full contract/provenance/timing.
- `diffusers`: attempts real model execution via `diffusers` + `torch` on a GPU runtime.

If `diffusers` dependencies are missing, the service returns explicit runtime errors (`runtime_unavailable`) rather than pretending generation succeeded.
