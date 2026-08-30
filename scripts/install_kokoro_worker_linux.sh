#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engines/kokoro_worker"
uv sync --inexact
