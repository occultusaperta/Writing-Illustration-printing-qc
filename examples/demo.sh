#!/usr/bin/env bash
set -euo pipefail

python -m bookforge doctor
python -m bookforge run --idea "a shy fox learns to paint" --pages 24 --size 8.5x8.5 --out dist/run1
