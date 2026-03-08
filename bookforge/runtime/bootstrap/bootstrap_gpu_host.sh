#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
if command -v sudo >/dev/null 2>&1; then
  APT_PREFIX="sudo"
else
  APT_PREFIX=""
fi
$APT_PREFIX apt-get update -y
$APT_PREFIX apt-get install -y python3 python3-venv python3-pip git build-essential

mkdir -p "$HOME/bookforge_runtime"
cd "$HOME/bookforge_runtime"
if [ ! -d Writing-Illustration-printing-qc ]; then
  git clone https://github.com/occultusaperta/Writing-Illustration-printing-qc.git
fi
cd Writing-Illustration-printing-qc
python3 -m venv "$HOME/bookforge_runtime/venv"
"$HOME/bookforge_runtime/venv/bin/pip" install --upgrade pip
