#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export HF_HOME="$ROOT_DIR/.hf_cache"
export HF_HUB_CACHE="$ROOT_DIR/.hf_cache/hub"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing Qwen3-TTS worker for Linux CUDA..."
cd engines/qwen_worker
uv sync --inexact

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Qwen worker Python not found: $PY" >&2
  exit 1
fi

PYTORCH_INDEX="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
uv pip install --python "$PY" qwen-tts
uv pip install --python "$PY" --force-reinstall torch --index-url "$PYTORCH_INDEX"

"$PY" - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY

echo "Qwen3-TTS Linux CUDA worker installed."
