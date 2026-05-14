from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


LanguageCode = Literal["auto", "vi", "en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]
OutputMode = Literal["merged", "split"]


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
    notes: str = ""


class ModelCapabilities(BaseModel):
    supported_languages: list[LanguageCode] = Field(default_factory=lambda: ["vi", "en"])
    supports_voice_profile: bool = True
    requires_voice_profile: bool = False
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
    speed: float = Field(default=1.0, ge=0.5, le=1.8)
    pitch_shift: float = Field(default=0.0, ge=-12.0, le=12.0)
    emotion: str = "natural"
    sentence_pause_ms: int = Field(default=450, ge=0, le=3000)
    max_chunk_chars: int = Field(default=220, ge=60, le=800)
    output_dir: Path | None = None
    output_stem: str | None = None
    source_path: Path | None = None
    overwrite: bool = False
    output_mode: OutputMode = "split"
    output_srt: bool = False


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
