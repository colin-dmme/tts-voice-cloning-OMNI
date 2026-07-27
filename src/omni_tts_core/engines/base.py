from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

import numpy as np
from omni_tts_shared.schemas import HiggsTtsOptions, RemoteEndpointOptions


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
    punctuation_pause_enabled: bool = False
    sentence_pause_ms: int = 0
    comma_pause_ms: int = 0
    clause_pause_ms: int = 0
    ellipsis_pause_ms: int = 0
    cancel_event: Event | None = None
    cached_prompt_path: Path | None = None  # asset dir for engine-level voice cache
    status_callback: Callable[[str], None] | None = None
    remote_endpoint: RemoteEndpointOptions | None = None
    higgs: HiggsTtsOptions | None = None


@dataclass(frozen=True)
class TtsEngineResult:
    audio: np.ndarray
    sample_rate: int


BatchProgressCallback = Callable[[int, int], None]
BatchChunkCallback = Callable[[int, Path], None]


class BaseTtsEngine:
    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        raise NotImplementedError

    def generate_batch(
        self,
        requests: list[TtsEngineRequest],
        progress_callback: BatchProgressCallback | None = None,
        chunk_callback: BatchChunkCallback | None = None,
    ) -> list[TtsEngineResult]:
        results = []
        total = len(requests)
        for index, request in enumerate(requests, start=1):
            results.append(self.generate(request))
            if progress_callback is not None:
                progress_callback(index, total)
        return results
