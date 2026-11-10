from __future__ import annotations

from typing import Callable

from colin_colab_remote.broker.failover import ConfirmSwitch, RemoteComputeCoordinator
from colin_colab_remote.broker.profiles import WorkerProfileStore
from colin_colab_remote.inference import _client_for_profile, _coordinator, generate_zerotts
from omni_tts_core.engines.base import (
    BaseTtsEngine,
    BatchChunkCallback,
    BatchProgressCallback,
    TtsEngineRequest,
    TtsEngineResult,
)
from omni_tts_core.engines.preset_onnx_engine import PresetOnnxSubprocessEngine
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT


CoordinatorFactory = Callable[..., RemoteComputeCoordinator]


class ZeroTtsRoutingEngine(BaseTtsEngine):
    def __init__(
        self,
        spec: ModelSpec,
        *,
        local_engine: BaseTtsEngine | None = None,
        profile_store: WorkerProfileStore | None = None,
        coordinator_factory: CoordinatorFactory | None = None,
        confirm_switch: ConfirmSwitch | None = None,
    ) -> None:
        self.spec = spec
        self.local_engine = local_engine or PresetOnnxSubprocessEngine(spec)
        self.profile_store = profile_store or WorkerProfileStore(
            PROJECT_ROOT / "config" / "remote_compute_workers.json"
        )
        self.coordinator_factory = coordinator_factory or _coordinator
        self.confirm_switch = confirm_switch

    def set_confirm_switch(self, callback: ConfirmSwitch | None) -> None:
        self.confirm_switch = callback

    def close(self) -> None:
        self.local_engine.close()

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        return self.generate_batch([request])[0]

    def generate_batch(
        self,
        requests: list[TtsEngineRequest],
        progress_callback: BatchProgressCallback | None = None,
        chunk_callback: BatchChunkCallback | None = None,
    ) -> list[TtsEngineResult]:
        if not requests:
            return []
        remote_flags = {request.runtime_target == "remote" for request in requests}
        if remote_flags == {False}:
            return self.local_engine.generate_batch(
                requests, progress_callback, chunk_callback
            )
        return generate_zerotts(self, requests, progress_callback, chunk_callback)
