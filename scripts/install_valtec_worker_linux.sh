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

echo "Installing Valtec worker for Linux..."
cd engines/valtec_worker
uv sync --inexact
mkdir -p vendor
if [[ ! -d vendor/valtec-tts/.git ]]; then
  git clone https://github.com/tronghieuit/valtec-tts.git vendor/valtec-tts
else
  git -C vendor/valtec-tts pull --ff-only
fi

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Valtec worker Python not found: $PY" >&2
  exit 1
fi

uv pip install --python "$PY" -e vendor/valtec-tts
uv pip install --python "$PY" torch --index-url https://download.pytorch.org/whl/cpu

echo "Valtec Linux worker installed."
