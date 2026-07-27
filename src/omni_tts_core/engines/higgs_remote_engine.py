from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.remote.higgs_sglang import HiggsSglangClient
from omni_tts_shared.errors import ConfigError, GenerationCancelled
from omni_tts_shared.schemas import HiggsTtsOptions


class HiggsRemoteEngine(BaseTtsEngine):
    """Thin engine bridge; HTTP and payload behavior live in ``core.remote``."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        if request.remote_endpoint is None:
            raise ConfigError("Thiếu cấu hình endpoint cho Higgs Remote.")
        options = request.higgs or HiggsTtsOptions()
        if request.cancel_event is not None and request.cancel_event.is_set():
            raise GenerationCancelled("Đã hủy tạo giọng.")
        client = HiggsSglangClient(request.remote_endpoint, options)
        if request.status_callback:
            request.status_callback("Đang gửi yêu cầu tới Higgs TTS 3 từ xa...")
        audio, sample_rate = client.synthesize(
            text=request.text,
            reference_audio_path=request.reference_audio_path,
            reference_text=request.reference_text,
        )
        if request.cancel_event is not None and request.cancel_event.is_set():
            raise GenerationCancelled("Đã hủy tạo giọng.")
        return TtsEngineResult(audio=audio, sample_rate=sample_rate)

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        if not requests:
            return []
        concurrency = max(1, min(16, (requests[0].higgs or HiggsTtsOptions()).concurrency))
        if concurrency == 1:
            return super().generate_batch(requests, progress_callback, chunk_callback)
        results: list[TtsEngineResult | None] = [None] * len(requests)
        completed = 0
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="higgs-remote") as pool:
            futures = {
                pool.submit(self.generate, request): index
                for index, request in enumerate(requests)
            }
            for future in as_completed(futures):
                index = futures[future]
                results[index] = future.result()
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(requests))
        return [item for item in results if item is not None]
