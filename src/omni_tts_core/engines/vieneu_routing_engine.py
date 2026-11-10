from __future__ import annotations

from colin_colab_remote.broker.profiles import WorkerProfileStore
from colin_colab_remote.inference import _coordinator, _read_batch, _reference_wave, generate_vieneu
from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine
from omni_tts_core.paths import PROJECT_ROOT


class VieneuRoutingEngine(BaseTtsEngine):
    def __init__(self, spec, cache=None, *, local_engine=None, profile_store=None, coordinator_factory=None, confirm_switch=None):
        self.spec = spec
        self.local_engine = local_engine or VieneuSubprocessEngine(spec, cache)
        self.profile_store = profile_store or WorkerProfileStore(PROJECT_ROOT / "config" / "remote_compute_workers.json")
        self.coordinator_factory = coordinator_factory or _coordinator
        self.confirm_switch = confirm_switch

    def set_confirm_switch(self, callback):
        self.confirm_switch = callback

    def close(self):
        self.local_engine.close()

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        return self.generate_batch([request])[0]

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        if not requests:
            return []
        targets = {request.runtime_target == "remote" for request in requests}
        if targets == {False}:
            return self.local_engine.generate_batch(requests, progress_callback, chunk_callback)
        return generate_vieneu(self, requests, progress_callback, chunk_callback)
