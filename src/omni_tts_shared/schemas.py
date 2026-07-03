from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


LanguageCode = Literal["auto", "vi", "en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
OutputMode = Literal["merged", "split"]
OutputAudioFormat = Literal["wav", "mp3"]
RuntimeTarget = Literal["auto", "cpu", "cuda"]


class ModelStatus(BaseModel):
    model_id: str
    display_name: str
    provider: str
    model_type: str
    hf_repo: str
    local_path: Path
    installed: bool
    required: bool = False
    size_mb: float = 0.0
    cache_size_mb: float = 0.0
    worker_size_mb: float = 0.0
    total_size_mb: float = 0.0
    notes: str = ""
    usage: str = ""
    category: str = ""
    storage_kind: str = ""
    storage_path: Path | None = None
    cache_path: Path | None = None
    worker_path: Path | None = None
    storage_note: str = ""
    worker_installed: bool | None = None  # None = không áp dụng (non-worker model)
    hf_cached: bool | None = None         # None = không áp dụng (non-worker model)


class ModelCapabilities(BaseModel):
    supported_languages: list[LanguageCode] = Field(default_factory=lambda: ["vi", "en"])
    supports_voice_profile: bool = True
    requires_voice_profile: bool = False
    supports_voice_presets: bool = False
    supports_reference_text: bool = True
    supports_speed: bool = False
    supports_pitch_shift: bool = False
    supports_emotion: bool = False
    emotions: list[str] = Field(default_factory=list)


class RuntimeStatus(BaseModel):
    model_id: str
    display_name: str
    provider: str
    installed: bool
    gpu_available: bool = False
    actual_device: str = "unknown"
    device_name: str = ""
    message: str = ""


class GenerateSpeechRequest(BaseModel):
    text: str = Field(min_length=1)
    language: LanguageCode = "vi"
    model_id: str = "omnivoice_vietnamese"
    voice_profile_id: str | None = None
    reference_audio_path: Path | None = None
    reference_text: str | None = None
    speaker_id: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=1.8)
    pitch_shift: float = Field(default=0.0, ge=-12.0, le=12.0)
    emotion: str = "natural"
    runtime_target: RuntimeTarget = "auto"
    codec_repo: str | None = None
    temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    top_k: int | None = Field(default=None, ge=1, le=200)
    f5_nfe_step: int | None = Field(default=None, ge=4, le=128)
    f5_cfg_strength: float | None = Field(default=None, ge=0.0, le=10.0)
    f5_sway_sampling_coef: float | None = Field(default=None, ge=-5.0, le=5.0)
    f5_cross_fade_duration: float | None = Field(default=None, ge=0.0, le=2.0)
    f5_target_rms: float | None = Field(default=None, ge=0.01, le=1.0)
    f5_remove_silence: bool = False
    f5_seed: int | None = Field(default=None, ge=0)
    f5_fix_duration: float | None = Field(default=None, ge=0.0, le=120.0)
    chatterbox_temperature: float | None = Field(default=None, ge=0.1, le=2.0)
    chatterbox_top_p: float | None = Field(default=None, ge=0.05, le=1.0)
    chatterbox_top_k: int | None = Field(default=None, ge=1, le=2000)
    chatterbox_repetition_penalty: float | None = Field(default=None, ge=1.0, le=3.0)
    chatterbox_seed: int | None = Field(default=None, ge=0)
    chatterbox_norm_loudness: bool = True
    sentence_pause_ms: int = Field(default=450, ge=0, le=3000)
    paragraph_pause_ms: int = Field(default=0, ge=0, le=10000)
    srt_file_padding_ms: int = Field(default=0, ge=0, le=10000)
    max_chunk_chars: int = Field(default=220, ge=60, le=800)
    output_dir: Path | None = None
    output_stem: str | None = None
    source_path: Path | None = None
    overwrite: bool = False
    output_mode: OutputMode = "split"
    output_audio_format: OutputAudioFormat = "wav"
    mp3_bitrate_kbps: int = Field(default=192, ge=64, le=320)
    output_srt: bool = False
    join_split_output_audio: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_pause_fields(cls, data):
        if isinstance(data, dict) and "paragraph_pause_ms" not in data and "srt_file_padding_ms" in data:
            data = dict(data)
            data["paragraph_pause_ms"] = data["srt_file_padding_ms"]
        return data

    @model_validator(mode="after")
    def sync_legacy_pause_field(self):
        self.srt_file_padding_ms = self.paragraph_pause_ms
        return self


class GenerateSpeechResult(BaseModel):
    job_id: str
    audio_path: Path
    srt_path: Path | None = None
    job_dir: Path
    segment_count: int
    duration_seconds: float
    message: str
    item_audio_paths: list[Path] = Field(default_factory=list)
    item_srt_paths: list[Path] = Field(default_factory=list)


class SegmentTiming(BaseModel):
    index: int
    text: str
    start_seconds: float
    end_seconds: float


class AudioSampleMeta(BaseModel):
    sample_id: str = ""
    role: str = "neutral"
    audio_path: Path
    transcript: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 0


class ProfileSaveWarning(BaseModel):
    code: str
    message: str


class RefAudioHints(BaseModel):
    min_seconds: float = 0.0
    max_seconds: float = 30.0
    optimal_min_seconds: float = 3.0
    optimal_max_seconds: float = 15.0
    needs_transcript: bool = False


class VoiceProfile(BaseModel):
    profile_id: str
    name: str
    audio_path: Path
    transcript: str = ""
    language: LanguageCode = "vi"
    project: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = 1
    duration_seconds: float = 0.0
    sample_rate: int = 0
    default_sample_id: str = ""
    extra_samples: list[AudioSampleMeta] = Field(default_factory=list)
