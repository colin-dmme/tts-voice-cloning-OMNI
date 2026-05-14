from __future__ import annotations

import json
from pathlib import Path

from omni_tts_core.paths import ensure_dir


DEFAULT_PREFERENCES = {
    "language": "vi",
    "model_id": "omnivoice_vietnamese",
    "voice_profile_id": None,
    "speaker_id": None,
    "output_dir": "",
    "output_stem": "",
    "speed": 1.0,
    "pitch_shift": 0.0,
    "emotion": "natural",
    "codec_repo": None,
    "temperature": None,
    "top_k": None,
    "sentence_pause_ms": 450,
    "max_chunk_chars": 220,
    "overwrite": False,
    "split_output": True,
    "output_srt": False,
}


class TkinterPreferences:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("config") / "ui_tkinter.json")

    def load(self) -> dict:
        if not self.path.exists():
            return dict(DEFAULT_PREFERENCES)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return dict(DEFAULT_PREFERENCES)
        merged = dict(DEFAULT_PREFERENCES)
        merged.update(data)
        return merged

    def save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
