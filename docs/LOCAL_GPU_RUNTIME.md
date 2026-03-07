# Local GPU Runtime (Rented Host)

This flow provisions and operates a rented GPU machine for `flux_local`.

## Required env vars

```bash
export BOOKFORGE_RUNTIME_PROVIDER=runpod
export RUNPOD_API_KEY=...                        # required for runpod provision/stop/destroy/status
export BOOKFORGE_RUNTIME_MAX_HOURLY_USD=1.2
export BOOKFORGE_RUNTIME_MIN_GPU_RAM_GB=16
export BOOKFORGE_RUNTIME_DISK_GB=80
export BOOKFORGE_RUNTIME_SSH_USER=root
export BOOKFORGE_RUNTIME_SSH_KEY_PATH=~/.ssh/id_rsa
export BOOKFORGE_RUNTIME_SERVICE_PORT=8188
```

Optional:

```bash
export BOOKFORGE_RUNTIME_STATE_PATH=.bookforge_runtime.json
export BOOKFORGE_RUNTIME_IMAGE=pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
export BOOKFORGE_FLUX_MODEL=black-forest-labs/FLUX.1-schnell
export BOOKFORGE_FLUX_RUNTIME_MODE=diffusers
export BOOKFORGE_GPU_BATCH_SCORING=true
```

If you still use Vast, keep `BOOKFORGE_RUNTIME_PROVIDER=vast_ai` and set `BOOKFORGE_VAST_API_KEY`.

## Commands

```bash
bookforge runtime-provision
bookforge runtime-bootstrap
bookforge runtime-launch
bookforge runtime-health --url http://<host>:8188/health
bookforge runtime-stop
bookforge runtime-destroy
```

Notes:
- `runtime-provision` saves selected offer + instance metadata to `.bookforge_runtime.json`.
- For `runpod`, provisioning selects GPU type `NVIDIA B200`, creates a pod, waits until `desiredStatus` is running, and records public SSH connection details.
- `runtime-bootstrap` copies and runs bootstrap scripts over SSH.
- `runtime-launch` starts `flux_local_service` and waits for `/health`.

## GPU batch scoring acceleration

Set `BOOKFORGE_GPU_BATCH_SCORING=true` to enable CUDA-native candidate scoring when `torch.cuda.is_available()` is true.

- Accelerated metrics: saliency/focal proxy, composition anchor score, texture/detail density proxies, and candidate ranking bonus.
- The QC payload records `gpu_batch_scores` including `cuda_used` per image so you can verify whether GPU kernels were actually used.
