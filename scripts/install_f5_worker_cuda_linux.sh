#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export HF_HOME="$ROOT/.hf_cache"
export HF_HUB_CACHE="$ROOT/.hf_cache/hub"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo "Installing isolated F5-TTS worker with CUDA PyTorch..."
cd engines/f5_worker
uv sync --inexact
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "F5-TTS worker Python not found: $PY"
  exit 1
fi
uv pip install --python "$PY" f5-tts
uv pip install --python "$PY" --reinstall torch==2.7.1+cu126 torchaudio==2.7.1+cu126 --index-url https://download.pytorch.org/whl/cu126
