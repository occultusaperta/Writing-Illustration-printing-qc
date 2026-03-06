# Local Flux Service Contract

BookForge now supports a structured local Flux HTTP contract used by `flux_local` provider.

## Endpoints

- `GET /health` → `{"status":"ok","service":"flux_local","supports":["/generate","/batch"]}`
- `POST /generate` request fields:
  - `prompt`, `width`, `height`
  - optional `negative_prompt`, `steps`, `seed`
  - optional `quality_preset`: `draft|premium|ultimate`
  - optional `reference_image` (base64 PNG)
  - optional `lora_slots` list
  - optional `spread` object
- `POST /batch` with `{ "requests": [ ...generate payloads... ] }`

## Response schema

`/generate` returns:

- `image_b64`
- `seed`
- `provider`
- `model`
- `elapsed_ms`
- `cache_key`
- `provenance` object

## Running scaffold service

A lightweight stub server exists for local contract testing:

```bash
python -m bookforge.illustration.providers.flux_local_service
```

Use env var:

```bash
export BOOKFORGE_IMAGE_PROVIDER=flux_local
export BOOKFORGE_FLUX_LOCAL_URL=http://127.0.0.1:8188/generate
```

This scaffold intentionally does not claim production-quality Flux rendering.
