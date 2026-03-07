# End-to-End: BookForge with Rented Flux Local Runtime

1) Provision a machine:

```bash
bookforge runtime-provision --max-hourly-usd 1.2 --min-gpu-ram-gb 16
```

2) Bootstrap machine software:

```bash
bookforge runtime-bootstrap
```

3) Launch the Flux local service:

```bash
bookforge runtime-launch --model black-forest-labs/FLUX.1-schnell
```

4) Test service health:

```bash
curl http://<runtime-host>:8188/health
```

5) Point BookForge to the runtime:

```bash
export BOOKFORGE_IMAGE_PROVIDER=flux_local
export BOOKFORGE_FLUX_LOCAL_URL=http://<runtime-host>:8188/generate
```

6) Run pipeline:

```bash
bookforge studio --story examples/sample_story.md --out out --illustrator flux_local --require-lock
```

## Honest limitations

- Provisioning and SSH automation are implemented and callable, but cannot be fully validated without real provider credentials and a reachable rented host.
- Real Flux generation requires GPU + `diffusers/torch` stack on that runtime (`BOOKFORGE_FLUX_RUNTIME_MODE=diffusers`).
- In local test environments, `fallback` mode is used so contract wiring can be verified without claiming production Flux quality.
