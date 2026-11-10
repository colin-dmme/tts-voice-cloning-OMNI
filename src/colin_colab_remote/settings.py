"""Colab preferences and data live independently of local model configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path

from filelock import FileLock
from pydantic import BaseModel, Field


def data_root() -> Path:
    override = os.environ.get("COLIN_COLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "ColinTTS" / "colab_remote"


class ColabSettings(BaseModel):
    enabled: bool = False
    account_id: str = Field(default="google-pro-1", pattern=r"^google-pro-[123]$")
    accelerator: str = Field(default="T4", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    max_runtime_minutes: int = Field(default=120, ge=5, le=600)
    startup_timeout_seconds: int = Field(default=1200, ge=60, le=3600)
    auto_release: bool = True
    start_broker: bool = True
    resume_at_logon: bool = True


class SettingsStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_root()
        self.path = self.directory / "settings.json"

    def load(self) -> ColabSettings:
        if not self.path.exists():
            return ColabSettings()
        return ColabSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: ColabSettings) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
