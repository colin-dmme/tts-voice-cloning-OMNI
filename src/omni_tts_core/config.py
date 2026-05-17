from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_shared.errors import ConfigError


def load_yaml_config(relative_path: str) -> dict[str, Any]:
    path = project_path(relative_path)
    if not path.exists():
        raise ConfigError(f"Không tìm thấy file cấu hình: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"File cấu hình không hợp lệ: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"File cấu hình phải là dạng key/value: {path}")
    return data


class AppSettings:
    def __init__(self, config_path: str = "config/app.yaml") -> None:
        self._data = load_yaml_config(config_path)

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def host(self) -> str:
        return str(self._data.get("app", {}).get("host", "127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self._data.get("app", {}).get("port", 7860))

    @property
    def app_name(self) -> str:
        return str(self._data.get("app", {}).get("name", "Colin TTS Local"))

    @property
    def app_version(self) -> str:
        value = self._data.get("app", {}).get("version", "")
        return "" if value is None else str(value).strip()

    @property
    def app_display_name(self) -> str:
        version = self.app_version
        if not version:
            return self.app_name
        return f"{self.app_name} v{version}"

    @property
    def contact_info(self) -> dict[str, str]:
        contact = self._data.get("app", {}).get("contact", {})
        if not isinstance(contact, dict):
            return {}
        return {str(key): "" if value is None else str(value) for key, value in contact.items()}

    @property
    def outputs_root(self) -> Path:
        value = self._data.get("paths", {}).get("outputs_root", "outputs/jobs")
        return project_path(str(value))

    @property
    def crossfade_ms(self) -> int:
        return int(self._data.get("generation", {}).get("crossfade_ms", 0))

    @property
    def generation_defaults(self) -> dict[str, Any]:
        return dict(self._data.get("generation", {}))
