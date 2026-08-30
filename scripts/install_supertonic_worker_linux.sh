#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engines/supertonic_worker"
uv sync --inexact
