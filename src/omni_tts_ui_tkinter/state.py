from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from omni_tts_shared.schemas import GenerateSpeechRequest


@dataclass
class UiSettings:
    language: str = "vi"
    model_id: str = "omnivoice_vietnamese"
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
    sentence_pause_ms: int = 450
    max_chunk_chars: int = 220
    output_dir: Path | None = None
    output_stem: str | None = None
    overwrite: bool = False
    split_output: bool = True
    output_srt: bool = False

    def to_request(self, text: str) -> GenerateSpeechRequest:
        return GenerateSpeechRequest(
            text=text,
            language=self.language,
            model_id=self.model_id,
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
            sentence_pause_ms=self.sentence_pause_ms,
            max_chunk_chars=self.max_chunk_chars,
            output_dir=self.output_dir,
            output_stem=self.output_stem,
            overwrite=self.overwrite,
            output_mode="split" if self.split_output else "merged",
            output_srt=self.output_srt,
        )
