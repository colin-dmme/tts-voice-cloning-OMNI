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

echo "Installing VieNeu worker for Linux CUDA..."
cd engines/vieneu_worker
uv sync --inexact

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "VieNeu worker Python not found: $PY" >&2
  exit 1
fi

PYTORCH_INDEX="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu126}"

echo "[1/5] Installing PyTorch CUDA..."
uv pip install --python "$PY" --force-reinstall torch torchaudio --index-url "$PYTORCH_INDEX"

echo "[2/5] Installing VieNeu package..."
uv pip install --python "$PY" --force-reinstall vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/

echo "[3/5] Installing ONNX Runtime GPU..."
uv pip uninstall --python "$PY" onnxruntime -y >/dev/null 2>&1 || true
uv pip install --python "$PY" --force-reinstall onnxruntime-gpu

echo "[4/5] Installing neucodec and Hugging Face helpers..."
uv pip install --python "$PY" --force-reinstall neucodec
uv pip install --python "$PY" huggingface_hub

echo "[5/5] Re-applying PyTorch CUDA after dependencies..."
uv pip install --python "$PY" --force-reinstall torch torchaudio --index-url "$PYTORCH_INDEX"

"$PY" - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY

echo "VieNeu Linux CUDA worker installed."
