from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omni_tts_core.config import load_yaml_config
from omni_tts_core.storage_paths import resolve_model_path
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import ModelCapabilities, RefAudioHints


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    provider: str
    model_type: str
    local_path: Path
    hf_repo: str
    language_priority: str
    required: bool = False
    notes: str = ""
    runtime: dict[str, Any] = field(default_factory=dict)
    catalog_info: dict[str, Any] = field(default_factory=dict)
    voice_presets: dict[str, str] = field(default_factory=dict)
    default_voice_preset: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    ref_audio_hints: RefAudioHints = field(default_factory=RefAudioHints)


class ModelRegistry:
    def __init__(self, config_path: str = "config/models.yaml") -> None:
        self._config_path = config_path
        self._models = self._load_models()

    def all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def tts_models(self) -> list[ModelSpec]:
        return [item for item in self.all() if item.model_type == "tts"]

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise ConfigError(f"Model chưa được khai báo: {model_id}") from exc

    def _load_models(self) -> dict[str, ModelSpec]:
        data = load_yaml_config(self._config_path)
        merged: dict[str, dict] = {}
        merged.update(data.get("tts_models", {}) or {})
        merged.update(data.get("support_models", {}) or {})
        models: dict[str, ModelSpec] = {}
        for model_id, raw in merged.items():
            models[model_id] = self._parse_model(model_id, raw)
        return models

    @staticmethod
    def _parse_model(model_id: str, raw: dict) -> ModelSpec:
        required_keys = ["display_name", "provider", "model_type", "local_path", "hf_repo"]
        missing = [key for key in required_keys if key not in raw]
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(f"Model {model_id} thiếu cấu hình: {joined}")
        return ModelSpec(
            model_id=model_id,
            display_name=str(raw["display_name"]),
            provider=str(raw["provider"]),
            model_type=str(raw["model_type"]),
            local_path=resolve_model_path(str(raw["local_path"])),
            hf_repo=str(raw["hf_repo"]),
            language_priority=str(raw.get("language_priority", "multilingual")),
            required=bool(raw.get("required", False)),
            notes=str(raw.get("notes", "")),
            runtime=dict(raw.get("runtime", {}) or {}),
            catalog_info=dict(raw.get("catalog_info", {}) or {}),
            voice_presets={
                str(key): str(value)
                for key, value in (raw.get("voice_presets", {}) or {}).items()
            },
            default_voice_preset=(
                None
                if raw.get("default_voice_preset") is None
                else str(raw.get("default_voice_preset"))
            ),
            capabilities=ModelCapabilities(**(raw.get("capabilities", {}) or {})),
            ref_audio_hints=RefAudioHints(**(raw.get("ref_audio_hints", {}) or {})),
        )
