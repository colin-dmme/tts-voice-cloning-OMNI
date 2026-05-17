from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

import numpy as np


@dataclass(frozen=True)
class TtsEngineRequest:
    text: str
    language: str
    reference_audio_path: Path | None
    reference_text: str | None
    speaker_id: str | None
    speed: float
    pitch_shift: float
    emotion: str = "natural"
    runtime_target: str = "auto"
    codec_repo: str | None = None
    temperature: float | None = None
    top_k: int | None = None
    cancel_event: Event | None = None
    cached_prompt_path: Path | None = None  # asset dir for engine-level voice cache


@dataclass(frozen=True)
class TtsEngineResult:
    audio: np.ndarray
    sample_rate: int


class BaseTtsEngine:
    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        raise NotImplementedError

    def generate_batch(self, requests: list[TtsEngineRequest]) -> list[TtsEngineResult]:
        return [self.generate(r) for r in requests]
