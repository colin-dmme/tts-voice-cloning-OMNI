from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.engines.base import TtsEngineRequest, TtsEngineResult
from omni_tts_core.remote_compute.failover import RemoteExecutionOutcome
from omni_tts_core.remote_compute.models import (
    WorkerProfile,
    WorkerSelectionSettings,
)
from omni_tts_core.remote_compute.profiles import (
    WorkerProfileDocument,
    WorkerProfileStore,
)
from omni_tts_core.service import TtsService
from omni_tts_core.ui_presenters.settings_state import GenerationSettings


class FakeLocalEngine:
    def __init__(self) -> None:
        self.requests: list[TtsEngineRequest] = []

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        self.requests.extend(requests)
        return [
            TtsEngineResult(audio=np.array([0.25], dtype=np.float32), sample_rate=24000)
            for _request in requests
        ]

    def close(self) -> None:
        return None


class FakeCoordinator:
    def __init__(self) -> None:
        self.requests = []

    def execute(self, request, destination, *, cancel_event=None):
        self.requests.append(request)
        sf.write(destination, np.array([0.1, -0.1], dtype=np.float32), 48000)
        return RemoteExecutionOutcome(
            destination=destination,
            initial_profile_id="google-pro-1",
            final_profile_id="google-pro-2",
            attempted_profile_ids=("google-pro-1", "google-pro-2"),
            failover_reasons=("runtime disconnected",),
        )


class FakeConfirmableEngine(FakeLocalEngine):
    def __init__(self) -> None:
        super().__init__()
        self.confirm_switch = None

    def set_confirm_switch(self, callback) -> None:
        self.confirm_switch = callback


class ZeroTtsRoutingEngineTest(unittest.TestCase):
    def _store(self, root: Path) -> WorkerProfileStore:
        store = WorkerProfileStore(root / "workers.json")
        store.save(
            WorkerProfileDocument(
                profiles=[
                    WorkerProfile(
                        profile_id="google-pro-1",
                        label="Google Pro 1",
                        broker_url="https://broker.test",
                        worker_id="google-pro-1",
                    ),
                    WorkerProfile(
                        profile_id="google-pro-2",
                        label="Google Pro 2",
                        broker_url="https://broker.test",
                        worker_id="google-pro-2",
                    ),
                ],
                selection=WorkerSelectionSettings(
                    selected_profile_id="google-pro-1",
                    switch_policy="automatic_failover",
                ),
            )
        )
        return store

    def test_remote_target_uses_coordinator_and_returns_remote_wave(self) -> None:
        try:
            from omni_tts_core.engines.zerotts_routing_engine import ZeroTtsRoutingEngine
        except ModuleNotFoundError as error:
            self.fail(f"Thiếu ZeroTtsRoutingEngine: {error}")
        with tempfile.TemporaryDirectory() as temp:
            coordinator = FakeCoordinator()
            local = FakeLocalEngine()
            engine = ZeroTtsRoutingEngine(
                SimpleNamespace(model_id="zerotts_202m_official"),
                local_engine=local,
                profile_store=self._store(Path(temp)),
                coordinator_factory=lambda _document, **_kwargs: coordinator,
            )

            result = engine.generate(
                TtsEngineRequest(
                    text="Xin chào",
                    language="vi",
                    reference_audio_path=None,
                    reference_text=None,
                    speaker_id="maichi",
                    speed=1.0,
                    pitch_shift=0.0,
                    runtime_target="remote",
                    provider_options={"audio_topk": 25},
                )
            )

        self.assertEqual(result.sample_rate, 48000)
        self.assertEqual(local.requests, [])
        self.assertEqual(coordinator.requests[0].speaker_id, "maichi")
        self.assertEqual(coordinator.requests[0].provider_options["audio_topk"], 25)

    def test_local_target_keeps_existing_local_engine(self) -> None:
        try:
            from omni_tts_core.engines.zerotts_routing_engine import ZeroTtsRoutingEngine
        except ModuleNotFoundError as error:
            self.fail(f"Thiếu ZeroTtsRoutingEngine: {error}")
        with tempfile.TemporaryDirectory() as temp:
            coordinator = FakeCoordinator()
            local = FakeLocalEngine()
            engine = ZeroTtsRoutingEngine(
                SimpleNamespace(model_id="zerotts_202m_official"),
                local_engine=local,
                profile_store=self._store(Path(temp)),
                coordinator_factory=lambda _document, **_kwargs: coordinator,
            )
            result = engine.generate(
                TtsEngineRequest(
                    text="Local",
                    language="vi",
                    reference_audio_path=None,
                    reference_text=None,
                    speaker_id="maichi",
                    speed=1.0,
                    pitch_shift=0.0,
                    runtime_target="cpu",
                )
            )

        self.assertEqual(result.sample_rate, 24000)
        self.assertEqual(len(local.requests), 1)
        self.assertEqual(coordinator.requests, [])

    def test_remote_target_does_not_require_local_zerotts_model(self) -> None:
        service = TtsService()
        spec = service.registry.get("zerotts_202m_official")
        try:
            remote_request = GenerationSettings(
                model_id=spec.model_id,
                runtime_target="remote",
                speaker_id="maichi",
            ).to_request("Xin chào")
        except Exception as error:
            self.fail(f"GenerateSpeechRequest phải nhận runtime_target remote: {error}")

        with patch.object(service.storage, "is_installed", return_value=False):
            try:
                service._ensure_request_can_generate(remote_request, spec)
            except Exception as error:
                self.fail(f"Remote ZeroTTS không được đòi model local: {error}")

    def test_service_forwards_switch_confirmation_to_cached_routing_engine(self) -> None:
        service = TtsService()
        spec = service.registry.get("zerotts_202m_official")
        engine = FakeConfirmableEngine()
        service._engines[spec.model_id] = engine
        callback = lambda _old, _new, _reason: True

        service.set_remote_switch_confirm(callback)
        resolved = service._engine_for(spec)

        self.assertIs(resolved, engine)
        self.assertIs(engine.confirm_switch, callback)


if __name__ == "__main__":
    unittest.main()
