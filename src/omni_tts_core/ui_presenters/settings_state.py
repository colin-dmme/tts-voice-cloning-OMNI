"""GenerationSettings: a UI-agnostic snapshot of the generation form.

Mirrors the tkinter UiSettings dataclass field-for-field and produces a core
GenerateSpeechRequest. Any GUI binds its widgets to these fields and calls
``to_request`` — no request-building logic lives in the GUI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from omni_tts_shared.schemas import GenerateSpeechRequest


# Default preference values for every generation field. Window/layout keys are
# GUI-specific and live in each GUI's own preferences store, not here.
DEFAULT_GENERATION_PREFERENCES: dict[str, Any] = {
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
}

# Keys that carry a filesystem path and round-trip as strings in preferences.
_PATH_KEYS = {"output_dir"}


@dataclass
class GenerationSettings:
    language: str = "vi"
    model_id: str = "omnivoice_vietnamese"
    voice_source_mode: str = "fixed"
    voice_profile_id: str | None = None
    reference_audio_path: Path | None = None
    reference_text: str = ""
    speaker_id: str | None = None
    speed: float = 1.0
    pitch_shift: float = 0.0
    emotion: str = "natural"
    runtime_target: str = "auto"
    codec_repo: str | None = None
    temperature: float | None = None
    top_k: int | None = None
    f5_nfe_step: int | None = None
    f5_cfg_strength: float | None = None
    f5_sway_sampling_coef: float | None = None
    f5_cross_fade_duration: float | None = None
    f5_target_rms: float | None = None
    f5_remove_silence: bool = False
    f5_seed: int | None = None
    f5_fix_duration: float | None = None
    chatterbox_temperature: float | None = None
    chatterbox_top_p: float | None = None
    chatterbox_top_k: int | None = None
    chatterbox_repetition_penalty: float | None = None
    chatterbox_seed: int | None = None
    chatterbox_norm_loudness: bool = True
    gpu_safety_enabled: bool = True
    gpu_start_temperature_c: int | None = None
    gpu_abort_temperature_c: int | None = None
    gpu_abort_temperature_sustain_seconds: float | None = None
    gpu_emergency_temperature_c: int | None = None
    gpu_cooldown_max_wait_seconds: float | None = None
    gpu_resume_temperature_c: int | None = None
    gpu_minimum_free_vram_mb: int | None = None
    gpu_runtime_minimum_free_vram_mb: int | None = None
    gpu_maximum_utilization_percent: int | None = None
    gpu_maximum_encoder_utilization_percent: int | None = None
    punctuation_pause_enabled: bool = True
    sentence_pause_ms: int = 320
    comma_pause_ms: int = 90
    clause_pause_ms: int = 180
    ellipsis_pause_ms: int = 450
    chunk_pause_ms: int = 120
    paragraph_pause_ms: int = 600
    srt_file_padding_ms: int = 0
    max_chunk_chars: int = 220
    output_dir: Path | None = None
    output_stem: str | None = None
    overwrite: bool = False
    split_output: bool = True
    output_audio_format: str = "wav"
    mp3_bitrate_kbps: int = 192
    output_srt: bool = False
    join_split_output_audio: bool = False

    def to_request(self, text: str) -> GenerateSpeechRequest:
        return GenerateSpeechRequest(
            text=text,
            language=self.language,
            model_id=self.model_id,
            voice_source_mode=self.voice_source_mode,
            voice_profile_id=self.voice_profile_id,
            reference_audio_path=self.reference_audio_path,
            reference_text=self.reference_text.strip() or None,
            speaker_id=self.speaker_id,
            speed=self.speed,
            pitch_shift=self.pitch_shift,
            emotion=self.emotion,
            runtime_target=self.runtime_target,
            codec_repo=self.codec_repo,
            temperature=self.temperature,
            top_k=self.top_k,
            f5_nfe_step=self.f5_nfe_step,
            f5_cfg_strength=self.f5_cfg_strength,
            f5_sway_sampling_coef=self.f5_sway_sampling_coef,
            f5_cross_fade_duration=self.f5_cross_fade_duration,
            f5_target_rms=self.f5_target_rms,
            f5_remove_silence=self.f5_remove_silence,
            f5_seed=self.f5_seed,
            f5_fix_duration=self.f5_fix_duration,
            chatterbox_temperature=self.chatterbox_temperature,
            chatterbox_top_p=self.chatterbox_top_p,
            chatterbox_top_k=self.chatterbox_top_k,
            chatterbox_repetition_penalty=self.chatterbox_repetition_penalty,
            chatterbox_seed=self.chatterbox_seed,
            chatterbox_norm_loudness=self.chatterbox_norm_loudness,
            gpu_safety_enabled=self.gpu_safety_enabled,
            gpu_start_temperature_c=self.gpu_start_temperature_c,
            gpu_abort_temperature_c=self.gpu_abort_temperature_c,
            gpu_abort_temperature_sustain_seconds=self.gpu_abort_temperature_sustain_seconds,
            gpu_emergency_temperature_c=self.gpu_emergency_temperature_c,
            gpu_cooldown_max_wait_seconds=self.gpu_cooldown_max_wait_seconds,
            gpu_resume_temperature_c=self.gpu_resume_temperature_c,
            gpu_minimum_free_vram_mb=self.gpu_minimum_free_vram_mb,
            gpu_runtime_minimum_free_vram_mb=self.gpu_runtime_minimum_free_vram_mb,
            gpu_maximum_utilization_percent=self.gpu_maximum_utilization_percent,
            gpu_maximum_encoder_utilization_percent=self.gpu_maximum_encoder_utilization_percent,
            punctuation_pause_enabled=self.punctuation_pause_enabled,
            sentence_pause_ms=self.sentence_pause_ms,
            comma_pause_ms=self.comma_pause_ms,
            clause_pause_ms=self.clause_pause_ms,
            ellipsis_pause_ms=self.ellipsis_pause_ms,
            chunk_pause_ms=self.chunk_pause_ms,
            paragraph_pause_ms=self.paragraph_pause_ms,
            # Kept in sync with paragraph_pause_ms for parity with the legacy UI;
            # a coordinated fix would decouple these two knobs.
            srt_file_padding_ms=self.paragraph_pause_ms,
            max_chunk_chars=self.max_chunk_chars,
            output_dir=self.output_dir,
            output_stem=self.output_stem,
            overwrite=self.overwrite,
            output_mode="split" if self.split_output else "merged",
            output_audio_format=self.output_audio_format,
            mp3_bitrate_kbps=self.mp3_bitrate_kbps,
            output_srt=self.output_srt,
            join_split_output_audio=self.join_split_output_audio,
        )

    @classmethod
    def from_preferences(cls, data: dict[str, Any]) -> "GenerationSettings":
        merged = dict(DEFAULT_GENERATION_PREFERENCES)
        saved = {key: value for key, value in data.items() if key in merged}
        if "chunk_pause_ms" not in saved and "sentence_pause_ms" in saved:
            saved["chunk_pause_ms"] = saved["sentence_pause_ms"]
        merged.update(saved)
        field_names = {field.name for field in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in merged.items():
            if key not in field_names:
                continue
            if key in _PATH_KEYS:
                text = str(value or "").strip()
                kwargs[key] = Path(text) if text else None
            else:
                kwargs[key] = value
        return cls(**kwargs)

    def to_preferences(self) -> dict[str, Any]:
        data = asdict(self)
        payload: dict[str, Any] = {}
        for key in DEFAULT_GENERATION_PREFERENCES:
            if key not in data:
                continue
            value = data[key]
            if key in _PATH_KEYS:
                value = str(value) if value else ""
            elif isinstance(value, Path):
                value = str(value)
            payload[key] = value
        return payload
