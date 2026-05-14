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
    speed: float
    pitch_shift: float
    emotion: str = "natural"
    cancel_event: Event | None = None


@dataclass(frozen=True)
class TtsEngineResult:
    audio: np.ndarray
    sample_rate: int


class BaseTtsEngine:
    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        raise NotImplementedError
