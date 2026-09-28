#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engines/zerotts_gguf_worker"
uv sync --inexact
.venv/bin/python build_native.py
