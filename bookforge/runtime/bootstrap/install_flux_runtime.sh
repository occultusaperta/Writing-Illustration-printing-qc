#!/usr/bin/env bash
set -euo pipefail

if [ ! -d "$HOME/bookforge_runtime/Writing-Illustration-printing-qc" ]; then
  echo "Repository missing at ~/bookforge_runtime/Writing-Illustration-printing-qc" >&2
  exit 1
fi

source "$HOME/bookforge_runtime/venv/bin/activate"
cd "$HOME/bookforge_runtime/Writing-Illustration-printing-qc"
pip install -e .

# Optional runtime packages for actual FLUX generation.
# The service works without these (falls back to deterministic placeholder image generation).
pip install "torch>=2.4" "diffusers>=0.31" "transformers>=4.45" accelerate safetensors
