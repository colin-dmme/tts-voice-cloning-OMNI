#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engines/zerotts_worker"
uv sync --inexact
