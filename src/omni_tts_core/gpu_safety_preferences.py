"""Shared GPU-safety preferences used by every application entry point."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omni_tts_core.paths import project_path
from omni_tts_core.ui_presenters.settings_state import DEFAULT_GENERATION_PREFERENCES


GPU_SAFETY_FIELDS: tuple[str, ...] = (
    "gpu_safety_enabled",
    "gpu_start_temperature_c",
    "gpu_abort_temperature_c",
    "gpu_abort_temperature_sustain_seconds",
    "gpu_emergency_temperature_c",
    "gpu_cooldown_max_wait_seconds",
    "gpu_resume_temperature_c",
    "gpu_minimum_free_vram_mb",
    "gpu_runtime_minimum_free_vram_mb",
    "gpu_maximum_utilization_percent",
    "gpu_maximum_encoder_utilization_percent",
)


def gpu_safety_values(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a complete GPU-safety mapping, ignoring unrelated keys."""
    normalized = {
        key: DEFAULT_GENERATION_PREFERENCES[key] for key in GPU_SAFETY_FIELDS
    }
    if values:
        normalized.update(
            {key: values[key] for key in GPU_SAFETY_FIELDS if key in values}
        )
    return normalized


class GpuSafetyPreferences:
    """Persist GPU thresholds independently from any one UI's preferences."""

    def __init__(
        self,
        path: Path | None = None,
        legacy_paths: tuple[Path, ...] | None = None,
    ) -> None:
        self.path = path or project_path("config/gpu_safety.json")
        self.legacy_paths = legacy_paths or (
            project_path("config/ui_qt.json"),
            project_path("config/ui_tkinter.json"),
        )

    def load(
        self, fallback: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        data = self._read_mapping(self.path)
        if data is not None:
            return gpu_safety_values(data)
        if fallback is not None:
            return gpu_safety_values(fallback)
        for legacy_path in self.legacy_paths:
            data = self._read_mapping(legacy_path)
            if data is not None:
                return gpu_safety_values(data)
        return gpu_safety_values()

    def save(self, values: Mapping[str, Any]) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary_path.write_text(
                json.dumps(gpu_safety_values(values), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True

    @staticmethod
    def _read_mapping(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None