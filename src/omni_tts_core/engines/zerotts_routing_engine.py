from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Callable

import soundfile as sf

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
from omni_tts_core.progress import check_cancel
from omni_tts_core.remote_compute.client import BrokerClient
from omni_tts_core.remote_compute.failover import (
    ConfirmSwitch,
    RemoteComputeCoordinator,
)
from omni_tts_core.remote_compute.models import (
    BrokerConnectionOptions,
    RemoteTtsRequest,
    WorkerProfile,
)
from omni_tts_core.remote_compute.profiles import (
    WorkerProfileDocument,
    WorkerProfileStore,
)
from omni_tts_shared.errors import GenerationError


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
        if len(remote_flags) != 1:
            raise GenerationError("Không được trộn local và remote trong cùng một batch.")

        document = self.profile_store.load()
        status_callback = requests[0].status_callback
        coordinator = self.coordinator_factory(
            document,
            confirm_switch=self.confirm_switch,
            status_callback=status_callback,
        )
        client_job_id = uuid.uuid4().hex
        results: list[TtsEngineResult] = []
        outputs_root = PROJECT_ROOT / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="zerotts-remote-", dir=outputs_root) as folder:
            root = Path(folder)
            total = len(requests)
            for index, engine_request in enumerate(requests, start=1):
                check_cancel(engine_request.cancel_event)
                inference_unit_id = f"chunk-{index:04d}"
                remote_request = RemoteTtsRequest(
                    client_job_id=client_job_id,
                    inference_unit_id=inference_unit_id,
                    idempotency_key=f"{client_job_id}:{inference_unit_id}",
                    model_id=self.spec.model_id,
                    text=engine_request.text,
                    language=engine_request.language,
                    speaker_id=engine_request.speaker_id,
                    provider_options=dict(engine_request.provider_options or {}),
                    metadata={"runtime_target": "remote"},
                )
                destination = root / f"chunk_{index:04d}.wav"
                coordinator.execute(
                    remote_request,
                    destination,
                    cancel_event=engine_request.cancel_event,
                )
                audio, sample_rate = sf.read(str(destination), dtype="float32")
                results.append(
                    TtsEngineResult(audio=audio, sample_rate=int(sample_rate))
                )
                if chunk_callback is not None:
                    chunk_callback(index, destination)
                if progress_callback is not None:
                    progress_callback(index, total)
        return results


def _coordinator(
    document: WorkerProfileDocument,
    *,
    confirm_switch: ConfirmSwitch | None,
    status_callback,
) -> RemoteComputeCoordinator:
    return RemoteComputeCoordinator(
        document,
        client_factory=_client_for_profile,
        confirm_switch=confirm_switch,
        status_callback=status_callback,
    )


def _client_for_profile(profile: WorkerProfile) -> BrokerClient:
    return BrokerClient(
        BrokerConnectionOptions(
            base_url=profile.broker_url,
            auth_env=profile.auth_env,
            auth_token_file=profile.auth_token_file,
        )
    )
