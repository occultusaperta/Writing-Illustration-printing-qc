# Premium Visual QC

## Visual Ensemble Evaluation

Packet 5 adds a non-blocking **Visual Ensemble Evaluation** stage that runs after color scoring and color post-processing in candidate QC. It computes multi-critic quality signals and attaches them to candidate metadata without changing ranking logic.

### Critics

- **composition_score (0-1)**
  - Uses a saliency proxy from gradient energy.
  - Evaluates focal-point placement, rule-of-thirds proximity, and third-grid edge-density balance.
- **clarity_score (0-1)**
  - Uses Laplacian variance as a sharpness estimator.
  - Normalized with a bounded response for stable ranges.
- **texture_score (0-1)**
  - Uses FFT energy distribution.
  - Measures high-frequency detail ratio versus total spectral energy.
- **artifact_score (0-1)**
  - Uses heuristic artifact detectors:
    - banding in smooth regions,
    - noise spikes from extreme local deviation,
    - compression/blocking via 8px boundary discontinuity.
  - Lower artifact severity yields a higher score.
- **perceptual_quality (0-1)**
  - Uses SSIM against a lightly blurred reference to estimate structural integrity.

### Ensemble Combination

Weighted sum:

- composition: `0.25`
- clarity: `0.20`
- texture: `0.15`
- artifact: `0.20`
- perceptual_quality: `0.20`

`ensemble_score = Σ(weight_i * critic_i)`

### GPU Batch Support

If CUDA is available and `torch` is present, batch evaluation can use GPU tensors for:

- saliency calculation,
- Laplacian clarity,
- FFT texture.

CPU/numpy fallback remains the default path.

### Metadata Attachment

Each candidate report receives:

```json
{
  "metadata": {
    "visual_ensemble": {
      "critic_scores": {
        "composition_score": 0.0,
        "clarity_score": 0.0,
        "texture_score": 0.0,
        "artifact_score": 0.0,
        "perceptual_quality": 0.0
      },
      "ensemble_score": 0.0
    }
  }
}
```

This packet does **not** re-rank candidates and does **not** trigger regeneration on its own.
