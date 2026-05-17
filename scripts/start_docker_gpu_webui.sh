#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INSTALL_VIENEU=1
INSTALL_QWEN=0
INSTALL_VALTEC=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-workers)
      INSTALL_VIENEU=0
      INSTALL_QWEN=0
      INSTALL_VALTEC=0
      ;;
    --qwen)
      INSTALL_QWEN=1
      ;;
    --valtec)
      INSTALL_VALTEC=1
      ;;
    --require-license)
      export COLIN_TTS_LICENSE_MODE="${COLIN_TTS_LICENSE_MODE:-required}"
      ;;
    --owner-license)
      export COLIN_TTS_LICENSE_MODE="disabled"
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

install_system_basics() {
  local missing=0
  for cmd in curl git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing=1
    fi
  done
  if [[ "$missing" == "0" ]]; then
    return
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl git ca-certificates
  fi
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv was installed but is not on PATH." >&2
    exit 1
  fi
}

install_system_basics
ensure_uv

export COLIN_TTS_ROOT="$ROOT_DIR"
export COLIN_TTS_HOST="${COLIN_TTS_HOST:-0.0.0.0}"
export COLIN_TTS_PORT="${COLIN_TTS_PORT:-7860}"
export COLIN_TTS_LICENSE_MODE="${COLIN_TTS_LICENSE_MODE:-disabled}"
export HF_HOME="$ROOT_DIR/.hf_cache"
export HF_HUB_CACHE="$ROOT_DIR/.hf_cache/hub"
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo "Preparing Colin TTS Local for Docker GPU..."
uv sync --inexact

echo "Restoring Git-backed user state..."
uv run --no-sync python scripts/restore_user_state.py --force --force-settings || true

if [[ "$INSTALL_VIENEU" == "1" ]]; then
  bash scripts/install_vieneu_worker_cuda_linux.sh
fi
if [[ "$INSTALL_QWEN" == "1" ]]; then
  bash scripts/install_qwen_worker_cuda_linux.sh
fi
if [[ "$INSTALL_VALTEC" == "1" ]]; then
  bash scripts/install_valtec_worker_linux.sh
fi

echo ""
echo "Starting Colin TTS Local Web UI on 0.0.0.0:${COLIN_TTS_PORT}"
echo "Open the cloud provider URL for exposed port ${COLIN_TTS_PORT}."
exec uv run --no-sync omni-tts-gradio
