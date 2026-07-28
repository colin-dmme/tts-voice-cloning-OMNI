"""Named punctuation-pause profiles shared by every frontend."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from omni_tts_core.paths import ensure_dir
from omni_tts_core.ui_presenters.settings_state import DEFAULT_GENERATION_PREFERENCES
from omni_tts_shared.errors import OmniTtsError


@dataclass(frozen=True)
class PunctuationPauseFieldSpec:
    key: str
    label: str
    tooltip_key: str

    @property
    def fixed_field(self) -> str:
        return f"{self.key}_pause_ms"

    @property
    def random_field(self) -> str:
        return f"{self.key}_pause_random_enabled"

    @property
    def minimum_field(self) -> str:
        return f"{self.key}_pause_min_ms"

    @property
    def maximum_field(self) -> str:
        return f"{self.key}_pause_max_ms"


PUNCTUATION_PAUSE_FIELDS = (
    PunctuationPauseFieldSpec("sentence", "Cuối câu · . ? !", "sentence_pause"),
    PunctuationPauseFieldSpec("comma", "Dấu phẩy · ,", "comma_pause"),
    PunctuationPauseFieldSpec("clause", "Chấm phẩy / hai chấm · ; :", "clause_pause"),
    PunctuationPauseFieldSpec("ellipsis", "Dấu ba chấm · … / ...", "ellipsis_pause"),
)

PAUSE_PRESET_KEYS = (
    "punctuation_pause_enabled",
    *(
        field
        for spec in PUNCTUATION_PAUSE_FIELDS
        for field in (
            spec.fixed_field,
            spec.random_field,
            spec.minimum_field,
            spec.maximum_field,
        )
    ),
    "chunk_pause_ms",
    "paragraph_pause_ms",
)


@dataclass(frozen=True)
class PunctuationPausePreset:
    name: str
    values: dict[str, int | bool]


class PunctuationPausePresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("config") / "punctuation_pause_presets.json")

    def list_presets(self) -> list[PunctuationPausePreset]:
        return sorted(self._load(), key=lambda item: item.name.casefold())

    def save(self, name: str, values: Mapping[str, Any]) -> PunctuationPausePreset:
        preset = PunctuationPausePreset(_validate_name(name), normalize_pause_values(values))
        presets = [
            item
            for item in self._load()
            if item.name.casefold() != preset.name.casefold()
        ]
        presets.append(preset)
        self._write(presets)
        return preset

    def delete(self, name: str) -> bool:
        key = str(name or "").strip().casefold()
        presets = self._load()
        kept = [item for item in presets if item.name.casefold() != key]
        if len(kept) == len(presets):
            return False
        self._write(kept)
        return True

    def _load(self) -> list[PunctuationPausePreset]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        rows = payload.get("presets", []) if isinstance(payload, dict) else []
        result: list[PunctuationPausePreset] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                result.append(
                    PunctuationPausePreset(
                        _validate_name(row.get("name", "")),
                        normalize_pause_values(row.get("values", {})),
                    )
                )
            except (OmniTtsError, TypeError, ValueError):
                continue
        return result

    def _write(self, presets: list[PunctuationPausePreset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "presets": [
                {"name": item.name, "values": item.values} for item in presets
            ],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
        except OSError as error:
            raise OmniTtsError(f"Không lưu được preset ngắt nghỉ: {error}") from error


def normalize_pause_values(values: Mapping[str, Any]) -> dict[str, int | bool]:
    merged: dict[str, Any] = {
        key: DEFAULT_GENERATION_PREFERENCES[key] for key in PAUSE_PRESET_KEYS
    }
    merged.update({key: values[key] for key in PAUSE_PRESET_KEYS if key in values})
    normalized: dict[str, int | bool] = {}
    for key in PAUSE_PRESET_KEYS:
        if key.endswith("_enabled"):
            normalized[key] = bool(merged[key])
        else:
            normalized[key] = max(0, int(merged[key]))
    for spec in PUNCTUATION_PAUSE_FIELDS:
        if normalized[spec.minimum_field] > normalized[spec.maximum_field]:
            raise OmniTtsError(f"{spec.label}: giá trị Min không được lớn hơn Max.")
    return normalized


def _validate_name(name: Any) -> str:
    value = " ".join(str(name or "").split())
    if not value:
        raise OmniTtsError("Tên preset không được để trống.")
    if len(value) > 80:
        raise OmniTtsError("Tên preset không được dài quá 80 ký tự.")
    return value
