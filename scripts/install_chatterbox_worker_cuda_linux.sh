#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export HF_HOME="$ROOT/.hf_cache"
export HF_HUB_CACHE="$ROOT/.hf_cache/hub"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo "Installing isolated Chatterbox Turbo worker with CUDA PyTorch..."
cd engines/chatterbox_worker
uv sync --inexact --upgrade-package chatterbox-tts
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Chatterbox worker Python not found: $PY"
  exit 1
fi
uv pip install --python "$PY" --upgrade chatterbox-tts
uv pip install --python "$PY" "setuptools>=70.0.0,<81.0.0"
uv pip install --python "$PY" --reinstall torch==2.6.0+cu124 torchaudio==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
