"""GenerationSettings: a UI-agnostic snapshot of the generation form.

Mirrors the tkinter UiSettings dataclass field-for-field and produces a core
GenerateSpeechRequest. Any GUI binds its widgets to these fields and calls
``to_request`` — no request-building logic lives in the GUI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from omni_tts_shared.schemas import (
    GenerateSpeechRequest,
    HiggsTtsOptions,
    RemoteEndpointOptions,
)


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
    "sentence_pause_random_enabled": False,
    "sentence_pause_min_ms": 260,
    "sentence_pause_max_ms": 380,
    "comma_pause_ms": 90,
    "comma_pause_random_enabled": False,
    "comma_pause_min_ms": 70,
    "comma_pause_max_ms": 120,
    "clause_pause_ms": 180,
    "clause_pause_random_enabled": False,
    "clause_pause_min_ms": 140,
    "clause_pause_max_ms": 220,
    "ellipsis_pause_ms": 450,
    "ellipsis_pause_random_enabled": False,
    "ellipsis_pause_min_ms": 380,
    "ellipsis_pause_max_ms": 550,
    "chunk_pause_ms": 120,
    "paragraph_pause_ms": 600,
    "paragraph_pause_random_enabled": False,
    "paragraph_pause_min_ms": 500,
    "paragraph_pause_max_ms": 700,
    "srt_file_padding_ms": 0,
    "max_chunk_chars": 220,
    "overwrite": False,
    "split_output": True,
    "output_audio_format": "wav",
    "mp3_bitrate_kbps": 192,
    "output_srt": False,
    "join_split_output_audio": False,
    "remote_base_url": "",
    "remote_endpoint_id": "higgs-default",
    "remote_api_flavor": "sglang",
    "remote_auth_mode": "none",
    "remote_auth_env": "OMNI_TTS_REMOTE_API_KEY",
    "remote_connect_timeout_seconds": 10.0,
    "remote_request_timeout_seconds": 600.0,
    "remote_max_retries": 1,
    "higgs_model": "",
    "higgs_voice": "default",
    "higgs_stream": True,
    "higgs_response_format": "pcm",
    "higgs_max_new_tokens": 2048,
    "higgs_temperature": 1.0,
    "higgs_top_p": None,
    "higgs_top_k": None,
    "higgs_seed": None,
    "higgs_initial_codec_chunk_frames": 1,
    "higgs_concurrency": 1,
    "higgs_emotion": "",
    "higgs_style": "",
    "higgs_speed": "",
    "higgs_pitch": "",
    "higgs_expressiveness": "",
    "higgs_delivery_tags": "",
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
    sentence_pause_random_enabled: bool = False
    sentence_pause_min_ms: int = 260
    sentence_pause_max_ms: int = 380
    comma_pause_ms: int = 90
    comma_pause_random_enabled: bool = False
    comma_pause_min_ms: int = 70
    comma_pause_max_ms: int = 120
    clause_pause_ms: int = 180
    clause_pause_random_enabled: bool = False
    clause_pause_min_ms: int = 140
    clause_pause_max_ms: int = 220
    ellipsis_pause_ms: int = 450
    ellipsis_pause_random_enabled: bool = False
    ellipsis_pause_min_ms: int = 380
    ellipsis_pause_max_ms: int = 550
    chunk_pause_ms: int = 120
    paragraph_pause_ms: int = 600
    paragraph_pause_random_enabled: bool = False
    paragraph_pause_min_ms: int = 500
    paragraph_pause_max_ms: int = 700
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
    remote_base_url: str = ""
    remote_endpoint_id: str = "higgs-default"
    remote_api_flavor: str = "sglang"
    remote_auth_mode: str = "none"
    remote_auth_env: str = "OMNI_TTS_REMOTE_API_KEY"
    remote_connect_timeout_seconds: float = 10.0
    remote_request_timeout_seconds: float = 600.0
    remote_max_retries: int = 1
    higgs_model: str = ""
    higgs_voice: str = "default"
    higgs_stream: bool = True
    higgs_response_format: str = "pcm"
    higgs_max_new_tokens: int = 2048
    higgs_temperature: float | None = 1.0
    higgs_top_p: float | None = None
    higgs_top_k: int | None = None
    higgs_seed: int | None = None
    higgs_initial_codec_chunk_frames: int = 1
    higgs_concurrency: int = 1
    higgs_emotion: str = ""
    higgs_style: str = ""
    higgs_speed: str = ""
    higgs_pitch: str = ""
    higgs_expressiveness: str = ""
    higgs_delivery_tags: str = ""

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
            sentence_pause_random_enabled=self.sentence_pause_random_enabled,
            sentence_pause_min_ms=self.sentence_pause_min_ms,
            sentence_pause_max_ms=self.sentence_pause_max_ms,
            comma_pause_ms=self.comma_pause_ms,
            comma_pause_random_enabled=self.comma_pause_random_enabled,
            comma_pause_min_ms=self.comma_pause_min_ms,
            comma_pause_max_ms=self.comma_pause_max_ms,
            clause_pause_ms=self.clause_pause_ms,
            clause_pause_random_enabled=self.clause_pause_random_enabled,
            clause_pause_min_ms=self.clause_pause_min_ms,
            clause_pause_max_ms=self.clause_pause_max_ms,
            ellipsis_pause_ms=self.ellipsis_pause_ms,
            ellipsis_pause_random_enabled=self.ellipsis_pause_random_enabled,
            ellipsis_pause_min_ms=self.ellipsis_pause_min_ms,
            ellipsis_pause_max_ms=self.ellipsis_pause_max_ms,
            chunk_pause_ms=self.chunk_pause_ms,
            paragraph_pause_ms=self.paragraph_pause_ms,
            paragraph_pause_random_enabled=self.paragraph_pause_random_enabled,
            paragraph_pause_min_ms=self.paragraph_pause_min_ms,
            paragraph_pause_max_ms=self.paragraph_pause_max_ms,
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
            remote_endpoint=RemoteEndpointOptions(
                endpoint_id=self.remote_endpoint_id,
                api_flavor=self.remote_api_flavor,
                base_url=self.remote_base_url.strip(),
                auth_mode=self.remote_auth_mode,
                auth_env=self.remote_auth_env,
                connect_timeout_seconds=self.remote_connect_timeout_seconds,
                request_timeout_seconds=self.remote_request_timeout_seconds,
                max_retries=self.remote_max_retries,
            ),
            higgs=HiggsTtsOptions(
                model=self.higgs_model.strip() or None,
                voice=self.higgs_voice.strip() or "default",
                stream=self.higgs_stream,
                response_format=self.higgs_response_format,
                max_new_tokens=self.higgs_max_new_tokens,
                temperature=self.higgs_temperature,
                top_p=self.higgs_top_p,
                top_k=self.higgs_top_k,
                seed=self.higgs_seed,
                initial_codec_chunk_frames=self.higgs_initial_codec_chunk_frames,
                concurrency=self.higgs_concurrency,
                emotion=self.higgs_emotion,
                style=self.higgs_style,
                speed=self.higgs_speed,
                pitch=self.higgs_pitch,
                expressiveness=self.higgs_expressiveness,
                delivery_tags=self.higgs_delivery_tags,
            ),
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

    def to_snapshot(self) -> dict[str, Any]:
        """Serialize every generation field for an exact history restore."""
        return {
            key: _snapshot_value(value)
            for key, value in asdict(self).items()
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "GenerationSettings":
        """Restore a full history snapshot while tolerating older schemas."""
        if not isinstance(data, dict):
            return cls()
        field_names = {field.name for field in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key not in field_names:
                continue
            if key in {"output_dir", "reference_audio_path"}:
                text = str(value or "").strip()
                kwargs[key] = Path(text) if text else None
            else:
                kwargs[key] = value
        return cls(**kwargs)


def _snapshot_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _snapshot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_value(item) for item in value]
    return value
