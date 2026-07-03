from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from omni_tts_core.paths import project_path
from omni_tts_shared.errors import ConfigError


LOCAL_STORAGE_CONFIG = "config/storage.local.yaml"

_MODEL_ROOT_ENV = ("COLIN_TTS_MODELS_ROOT", "OMNI_TTS_MODELS_ROOT")
_HF_CACHE_ENV = ("COLIN_TTS_HF_CACHE_ROOT", "OMNI_TTS_HF_CACHE_ROOT")
_OUTPUTS_ROOT_ENV = ("COLIN_TTS_OUTPUTS_ROOT", "OMNI_TTS_OUTPUTS_ROOT")
_STORAGE_CONFIG_ENV = ("COLIN_TTS_STORAGE_CONFIG", "OMNI_TTS_STORAGE_CONFIG")


def models_root() -> Path:
    return _configured_path(_MODEL_ROOT_ENV, "models_root", "models")


def hf_cache_root() -> Path:
    return _configured_path(_HF_CACHE_ENV, "hf_cache_root", ".hf_cache")


def hf_hub_cache_root() -> Path:
    return hf_cache_root() / "hub"


def outputs_root(default: str | Path = "outputs/jobs") -> Path:
    return _configured_path(_OUTPUTS_ROOT_ENV, "outputs_root", default)


def resolve_model_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    parts = path.parts
    if parts and parts[0].lower() == "models":
        return (models_root().joinpath(*parts[1:])).resolve()
    return project_path(path).resolve()


def ensure_models_root() -> Path:
    root = models_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_hf_cache_root() -> Path:
    root = hf_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_hf_hub_cache_root() -> Path:
    root = hf_hub_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def hf_cache_env() -> dict[str, str]:
    root = ensure_hf_cache_root()
    hub = ensure_hf_hub_cache_root()
    return {
        "HF_HOME": str(root),
        "HF_HUB_CACHE": str(hub),
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
    }


def valtec_appdata_root() -> Path:
    return ensure_hf_cache_root() / "valtec_appdata"


def hf_repo_cache_dirs(hf_repo: str) -> list[Path]:
    folder = "models--" + hf_repo.replace("/", "--")
    root = hf_cache_root()
    return [
        root / "hub" / folder,
        root / folder,
    ]


def storage_roots() -> dict[str, Path]:
    return {
        "models": models_root(),
        "hf_cache": hf_cache_root(),
        "outputs": outputs_root(),
    }


def local_storage_config_path() -> Path:
    override = _first_env(_STORAGE_CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return project_path(LOCAL_STORAGE_CONFIG).resolve()


def _configured_path(env_names: tuple[str, ...], config_key: str, default: str | Path) -> Path:
    env_value = _first_env(env_names)
    if env_value:
        return _resolve_path(env_value)
    config_value = _storage_config().get(config_key)
    if config_value:
        return _resolve_path(str(config_value))
    return _resolve_path(default)


def _resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return project_path(path).resolve()


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return ""


def _storage_config() -> dict[str, Any]:
    path = local_storage_config_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"File cấu hình storage không hợp lệ: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"File cấu hình storage phải là key/value: {path}")
    storage = data.get("storage", data)
    return storage if isinstance(storage, dict) else {}
