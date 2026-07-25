"""QtPreferences: persist generation settings + window layout to config/ui_qt.json.

Reuses the shared DEFAULT_GENERATION_PREFERENCES so the Qt GUI and any future
GUI agree on generation defaults; window/layout keys are Qt-specific.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omni_tts_core.paths import ensure_dir
from omni_tts_core.ui_presenters.settings_state import DEFAULT_GENERATION_PREFERENCES

# Qt-only layout keys, merged on top of the shared generation defaults.
QT_LAYOUT_DEFAULTS: dict[str, Any] = {
    "window_geometry_b64": "",
    "window_state_b64": "",
    "main_splitter_b64": "",
    "settings_panel_collapsed": False,
    "chart_visible": True,
    "active_page": 0,
    "queue_status_filter": "all",
    "queue_search": "",
}

DEFAULT_QT_PREFERENCES: dict[str, Any] = {**DEFAULT_GENERATION_PREFERENCES, **QT_LAYOUT_DEFAULTS}


class QtPreferences:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("config") / "ui_qt.json")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_QT_PREFERENCES)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_QT_PREFERENCES)
        if not isinstance(data, dict):
            return dict(DEFAULT_QT_PREFERENCES)
        if "paragraph_pause_ms" not in data and "srt_file_padding_ms" in data:
            data["paragraph_pause_ms"] = data["srt_file_padding_ms"]
        if "chunk_pause_ms" not in data and "sentence_pause_ms" in data:
            data["chunk_pause_ms"] = data["sentence_pause_ms"]
        merged = dict(DEFAULT_QT_PREFERENCES)
        merged.update(data)
        return merged

    def save(self, data: dict[str, Any]) -> None:
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
