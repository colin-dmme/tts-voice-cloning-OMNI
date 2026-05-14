from __future__ import annotations

import os
from pathlib import Path


def _project_root() -> Path:
    override = os.environ.get("COLIN_TTS_ROOT") or os.environ.get("OMNI_TTS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _project_root()


def project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def ensure_dir(path: str | Path) -> Path:
    resolved = project_path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
