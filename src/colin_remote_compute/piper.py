from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.engines.piper_engine import piper_segments
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import GenerationError

from .broker.models import RemoteTtsRequest
from .context import managed_execution
from .inference_units import InferenceUnit, execute_units


def generate_piper(model_id, requests, progress_callback=None, chunk_callback=None):
    context = managed_execution()
    if context is None or not getattr(context.lifecycle, "is_existing_worker", False):
        raise GenerationError("Chọn CPU máy khác trong Studio để chạy Piper từ xa.")
    if any(request.runtime_target != "remote" for request in requests):
        raise GenerationError("Các đoạn Piper phải dùng cùng chế độ CPU từ xa.")
    job_id = context.next_call_id()
    results = []
    with tempfile.TemporaryDirectory(prefix="piper-cpu-remote-") as folder:
        def units():
            for index, request in enumerate(requests, 1):
                check_cancel(request.cancel_event)
                unit = f"chunk-{index:04d}"
                text_hash = hashlib.sha256(request.text.encode()).hexdigest()
                segments = context.freeze(f"{job_id}:{unit}:{text_hash}", lambda: piper_segments(request))
                remote = RemoteTtsRequest(
                    client_job_id=job_id, inference_unit_id=unit, idempotency_key=f"{job_id}:{unit}",
                    model_id=model_id, text=request.text, language=request.language, speaker_id=request.speaker_id,
                    segments=segments,
                    provider_options={
                        "speed": request.speed, "noise_scale": request.piper_noise_scale, "noise_w": request.piper_noise_w,
                        "seed": request.piper_seed,
                        "sentence_pause_ms": request.sentence_pause_ms if request.punctuation_pause_enabled else 0,
                    },
                )
                yield InferenceUnit(remote, Path(folder) / f"{unit}.wav", request.cancel_event)

        for index, unit in enumerate(execute_units(context, units()), 1):
            check_cancel(unit.cancel_event)
            destination = unit.destination
            audio, rate = sf.read(destination, dtype="float32")
            results.append(TtsEngineResult(audio=audio, sample_rate=rate))
            if chunk_callback is not None:
                chunk_callback(index, destination)
            if progress_callback is not None:
                progress_callback(index, len(requests))
    return results
