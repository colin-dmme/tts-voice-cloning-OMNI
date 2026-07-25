from __future__ import annotations

import json
from pathlib import Path

from omni_tts_core.paths import ensure_dir


DEFAULT_PREFERENCES = {
    "language": "vi",
    "model_id": "omnivoice_vietnamese",
    "voice_source_mode": "fixed",
    "voice_profile_id": None,
    "speaker_id": None,
    "output_dir": "",
    "output_stem": "",
    "speed": 1.0,
    "pitch_shift": 0.0,
    "emotion": "natural",
    "runtime_target": "auto",
    "codec_repo": None,
    "temperature": None,
    "top_k": None,
    "f5_nfe_step": None,
    "f5_cfg_strength": None,
    "f5_sway_sampling_coef": None,
    "f5_cross_fade_duration": None,
    "f5_target_rms": None,
    "f5_remove_silence": False,
    "f5_seed": None,
    "f5_fix_duration": None,
    "chatterbox_temperature": None,
    "chatterbox_top_p": None,
    "chatterbox_top_k": None,
    "chatterbox_repetition_penalty": None,
    "chatterbox_seed": None,
    "chatterbox_norm_loudness": True,
    "gpu_safety_enabled": True,
    "gpu_start_temperature_c": 75,
    "gpu_abort_temperature_c": 82,
    "gpu_abort_temperature_sustain_seconds": 10.0,
    "gpu_emergency_temperature_c": 90,
    "gpu_cooldown_max_wait_seconds": 300.0,
    "gpu_resume_temperature_c": 72,
    "gpu_minimum_free_vram_mb": 6000,
    "gpu_runtime_minimum_free_vram_mb": 700,
    "gpu_maximum_utilization_percent": 20,
    "gpu_maximum_encoder_utilization_percent": 5,
    "punctuation_pause_enabled": True,
    "sentence_pause_ms": 320,
    "comma_pause_ms": 90,
    "clause_pause_ms": 180,
    "ellipsis_pause_ms": 450,
    "chunk_pause_ms": 120,
    "paragraph_pause_ms": 600,
    "srt_file_padding_ms": 0,
    "max_chunk_chars": 220,
    "overwrite": False,
    "split_output": True,
    "output_audio_format": "wav",
    "mp3_bitrate_kbps": 192,
    "output_srt": False,
    "join_split_output_audio": False,
    "window_geometry": "",
    "window_state": "normal",
    "text_pane_sash": None,
    "text_pane_ratio": None,
    "file_pane_sash": None,
    "file_pane_ratio": None,
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
        if "voice_source_mode" not in data:
            data["voice_source_mode"] = (
                "profile" if data.get("voice_profile_id") else "fixed"
            )
        if "paragraph_pause_ms" not in data and "srt_file_padding_ms" in data:
            data["paragraph_pause_ms"] = data["srt_file_padding_ms"]
        if "chunk_pause_ms" not in data and "sentence_pause_ms" in data:
            data["chunk_pause_ms"] = data["sentence_pause_ms"]
        merged = dict(DEFAULT_PREFERENCES)
        merged.update(data)
        return merged

    def save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
