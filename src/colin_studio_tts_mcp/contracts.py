"""Stable transport contracts mapped onto UI-agnostic core settings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from omni_tts_core.gpu_safety_preferences import GPU_SAFETY_FIELDS
from omni_tts_core.ui_presenters.settings_state import GenerationSettings


VoiceMode = Literal["fixed", "profile", "design"]


class VoiceSelection(BaseModel):
    mode: VoiceMode = "fixed"
    voice_id: str | None = Field(default=None, max_length=200)

    @field_validator("voice_id")
    @classmethod
    def clean_voice_id(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @model_validator(mode="after")
    def require_library_voice(self):
        if self.mode in {"profile", "design"} and not self.voice_id:
            raise ValueError(f"voice_id là bắt buộc khi mode={self.mode}")
        return self


class OutputOptions(BaseModel):
    directory: str | None = None
    stem: str | None = Field(default=None, max_length=160)
    mode: Literal["merged", "split"] = "merged"
    audio_format: Literal["wav", "mp3"] = "wav"
    mp3_bitrate_kbps: int = Field(default=192, ge=64, le=320)
    create_srt: bool = False
    join_split_audio: bool = False
    append_voice_duration_suffix: bool = False

    @field_validator("stem")
    @classmethod
    def validate_stem(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if any(char in value for char in '<>:"/\\|?*'):
            raise ValueError("stem không được chứa ký tự dành riêng cho đường dẫn")
        if value in {".", ".."}:
            raise ValueError("stem không hợp lệ")
        return value

    @field_validator("directory")
    @classmethod
    def validate_directory(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("directory phải là đường dẫn tuyệt đối")
        resolved = path.resolve(strict=False)
        if resolved == Path(resolved.anchor):
            raise ValueError("Không cho phép dùng thư mục gốc của ổ đĩa làm output")
        return str(resolved)


class GenerationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="vi", min_length=2, max_length=16)
    runtime_target: Literal["auto", "cpu", "cuda", "remote"] = "auto"
    speed: float = Field(default=1.0, ge=0.5, le=1.8)
    pitch_shift: float = Field(default=0.0, ge=-12.0, le=12.0)
    emotion: str = Field(default="natural", max_length=100)
    max_chunk_chars: int = Field(default=220, ge=60, le=800)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    advanced: dict[str, Any] = Field(default_factory=dict)


class TextGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500_000)
    model_id: str = Field(min_length=1, max_length=200)
    voice: VoiceSelection = Field(default_factory=VoiceSelection)
    output: OutputOptions = Field(default_factory=OutputOptions)
    generation: GenerationOptions = Field(default_factory=GenerationOptions)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text không được để trống")
        return value

    def to_settings(
        self, gpu_preferences: Mapping[str, Any] | None = None
    ) -> GenerationSettings:
        return _to_settings(
            self.model_id,
            self.voice,
            self.output,
            self.generation,
            self.text,
            gpu_preferences,
        )


class FileGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_files: list[str] = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    voice: VoiceSelection = Field(default_factory=VoiceSelection)
    output: OutputOptions = Field(default_factory=lambda: OutputOptions(mode="split"))
    generation: GenerationOptions = Field(default_factory=GenerationOptions)

    @field_validator("source_files")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        resolved: list[str] = []
        seen: set[str] = set()
        for raw in values:
            path = Path(raw)
            if not path.is_absolute():
                raise ValueError(f"File nguồn phải là đường dẫn tuyệt đối: {raw}")
            try:
                path = path.resolve(strict=True)
            except OSError as exc:
                raise ValueError(f"Không tìm thấy file nguồn: {raw}") from exc
            if not path.is_file():
                raise ValueError(f"Không phải file: {path}")
            if path.suffix.lower() not in {".txt", ".md", ".srt"}:
                raise ValueError(f"Chỉ hỗ trợ TXT, Markdown hoặc SRT: {path}")
            if path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError(f"File vượt giới hạn 20 MB: {path}")
            key = str(path).casefold()
            if key not in seen:
                resolved.append(str(path))
                seen.add(key)
        return resolved

    def to_settings(
        self, gpu_preferences: Mapping[str, Any] | None = None
    ) -> GenerationSettings:
        return _to_settings(
            self.model_id,
            self.voice,
            self.output,
            self.generation,
            "Nội dung sẽ được đọc từ file nguồn.",
            gpu_preferences,
        )


_PROTECTED_SETTINGS = {
    "model_id", "language", "voice_source_mode", "voice_profile_id",
    "reference_audio_path", "reference_text", "speaker_id", "designed_voice_id",
    "output_dir", "output_stem", "append_stem_suffix", "overwrite", "split_output",
    "output_audio_format", "mp3_bitrate_kbps", "output_srt",
    "join_split_output_audio", "runtime_target", "speed", "pitch_shift", "emotion",
    "max_chunk_chars", "provider_options",
}
_SETTING_FIELDS = {item.name for item in fields(GenerationSettings)}


def advanced_setting_fields() -> list[str]:
    """Names accepted inside generation.advanced."""
    return sorted(_SETTING_FIELDS - _PROTECTED_SETTINGS)


def _to_settings(
    model_id: str,
    voice: VoiceSelection,
    output: OutputOptions,
    generation: GenerationOptions,
    validation_text: str,
    gpu_preferences: Mapping[str, Any] | None = None,
) -> GenerationSettings:
    unknown = set(generation.advanced) - (_SETTING_FIELDS - _PROTECTED_SETTINGS)
    if unknown:
        raise ValueError("advanced chứa trường không hỗ trợ: " + ", ".join(sorted(unknown)))
    values: dict[str, Any] = {}
    if gpu_preferences:
        values.update(
            {
                key: gpu_preferences[key]
                for key in GPU_SAFETY_FIELDS
                if key in gpu_preferences
            }
        )
    # Per-request advanced values deliberately take precedence over shared defaults.
    values.update(generation.advanced)
    values.update(
        model_id=model_id.strip(),
        language=generation.language,
        voice_source_mode=voice.mode,
        runtime_target=generation.runtime_target,
        speed=generation.speed,
        pitch_shift=generation.pitch_shift,
        emotion=generation.emotion,
        max_chunk_chars=generation.max_chunk_chars,
        provider_options=dict(generation.provider_options),
        output_dir=Path(output.directory) if output.directory else None,
        output_stem=output.stem,
        append_stem_suffix=output.append_voice_duration_suffix,
        overwrite=False,
        split_output=output.mode == "split",
        output_audio_format=output.audio_format,
        mp3_bitrate_kbps=output.mp3_bitrate_kbps,
        output_srt=output.create_srt,
        join_split_output_audio=output.join_split_audio,
    )
    if voice.mode == "fixed":
        values["speaker_id"] = voice.voice_id
    elif voice.mode == "profile":
        values["voice_profile_id"] = voice.voice_id
    else:
        values["designed_voice_id"] = voice.voice_id
    settings = GenerationSettings(**values)
    settings.to_request(validation_text)
    return settings
