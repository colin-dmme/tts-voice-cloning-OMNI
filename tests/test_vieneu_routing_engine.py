from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from omni_tts_core.engines.base import TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.vieneu_routing_engine import VieneuRoutingEngine
from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.remote_compute.profiles import WorkerProfileStore
from omni_tts_core.service import TtsService
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GenerationCancelled, GenerationError


class FakeLocal:
    def __init__(self):
        self.requests = []
        self.closed = False

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        self.requests.extend(requests)
        return [TtsEngineResult(np.zeros(100, dtype=np.float32), 48000) for _ in requests]

    def close(self):
        self.closed = True


class FakeCoordinator:
    def __init__(self):
        self.requests = []

    def execute(self, request, destination, **kwargs):
        self.requests.append((request, kwargs))
        with zipfile.ZipFile(destination, "w") as archive:
            for index, _text in enumerate(request.batch_texts, start=1):
                stream = io.BytesIO()
                sf.write(stream, np.ones(100) * index / 10, 48000, format="WAV", subtype="PCM_16")
                archive.writestr(f"chunk_{index:04d}.wav", stream.getvalue())


def request(**kwargs):
    values = dict(text="Xin chào", language="vi", reference_audio_path=None, reference_text=None,
                  speaker_id="Ngọc Huyền", speed=1.0, pitch_shift=0.0, runtime_target="remote")
    return TtsEngineRequest(**{**values, **kwargs})


def engine(tmp_path, coordinator):
    return VieneuRoutingEngine(
        ModelRegistry().get("vieneu_v3_turbo"), local_engine=FakeLocal(),
        profile_store=WorkerProfileStore(tmp_path / "profiles.json"),
        coordinator_factory=lambda *args, **kwargs: coordinator,
    )


def test_remote_preset_batches_chunks_and_reports_each_in_original_order(tmp_path):
    coordinator = FakeCoordinator()
    router = engine(tmp_path, coordinator)
    progress, chunks = [], []
    items = [request(text=f"Đoạn {index}") for index in range(6)]
    results = router.generate_batch(items, lambda n, total: progress.append((n, total)), lambda n, path: chunks.append((n, path.read_bytes())))
    assert len(results) == 6
    assert [len(item[0].batch_texts) for item in coordinator.requests] == [4, 2]
    assert coordinator.requests[0][0].speaker_id == "Ngọc Huyền"
    assert progress == [(index, 6) for index in range(1, 7)]
    assert len(chunks) == 6
    assert router.local_engine.requests == []
    assert [round(float(result.audio[0]), 1) for result in results] == [0.1, 0.2, 0.3, 0.4, 0.1, 0.2]


def test_clone_uploads_mono_pcm_reference_instead_of_leaking_local_path(tmp_path):
    reference = tmp_path / "my-private-voice.wav"
    sf.write(reference, np.ones((48000 * 3, 2)) * 0.05, 48000)
    coordinator = FakeCoordinator()
    result = engine(tmp_path, coordinator).generate(request(reference_audio_path=reference))
    remote, kwargs = coordinator.requests[0]
    audio = kwargs["reference_audio"]
    assert remote.reference_audio_id == hashlib.sha256(audio).hexdigest()
    assert remote.speaker_id is None
    assert reference.name not in remote.model_dump_json()
    assert sf.info(io.BytesIO(audio)).channels == 1
    assert sf.info(io.BytesIO(audio)).subtype == "PCM_16"
    assert result.sample_rate == 48000


def test_distinct_presets_or_sampling_are_never_merged_in_same_batch(tmp_path):
    coordinator = FakeCoordinator()
    engine(tmp_path, coordinator).generate_batch([request(), request(speaker_id="Minh Quân"), request(speaker_id="Minh Quân", temperature=0.6)])
    assert len(coordinator.requests) == 3
    assert coordinator.requests[-1][0].provider_options["temperature"] == 0.6


def test_local_route_and_close_preserve_existing_engine(tmp_path):
    coordinator = FakeCoordinator()
    router = engine(tmp_path, coordinator)
    router.generate(request(runtime_target="cpu"))
    router.close()
    assert len(router.local_engine.requests) == 1
    assert router.local_engine.closed
    assert coordinator.requests == []


def test_cancelled_remote_batch_does_not_submit(tmp_path):
    coordinator = FakeCoordinator()
    cancel = Event()
    cancel.set()
    with pytest.raises(GenerationCancelled):
        engine(tmp_path, coordinator).generate(request(cancel_event=cancel))
    assert coordinator.requests == []


def test_remote_v3_preset_and_clone_do_not_require_local_model(tmp_path):
    service = TtsService(settings=SimpleNamespace(outputs_root=tmp_path / "jobs", project_root=tmp_path, app_name="test", crossfade_ms=0))
    spec = service.registry.get("vieneu_v3_turbo")
    with patch.object(service.storage, "is_installed", return_value=False):
        for settings in (
            GenerationSettings(model_id=spec.model_id, runtime_target="remote", speaker_id="Ngọc Huyền"),
            GenerationSettings(model_id=spec.model_id, runtime_target="remote", voice_source_mode="profile", reference_audio_path=Path("voice.wav")),
        ):
            service._ensure_request_can_generate(settings.to_request("Xin chào"), spec)


@pytest.mark.parametrize("clone", [False, True])
def test_real_service_pipeline_saves_remote_v3_without_installed_local_model(tmp_path, clone):
    reference = tmp_path / "reference.wav"
    sf.write(reference, np.ones(24000 * 3) * 0.05, 24000)
    coordinator = FakeCoordinator()
    service = TtsService(settings=SimpleNamespace(outputs_root=tmp_path / "jobs", project_root=tmp_path, app_name="test", crossfade_ms=0))
    service._engines["vieneu_v3_turbo"] = engine(tmp_path, coordinator)
    settings = GenerationSettings(
        model_id="vieneu_v3_turbo", runtime_target="remote",
        voice_source_mode="profile" if clone else "fixed",
        reference_audio_path=reference if clone else None,
        speaker_id=None if clone else "Ngọc Huyền",
        output_dir=tmp_path / "output", output_stem="clone" if clone else "preset",
    )
    with patch.object(service.storage, "is_installed", return_value=False):
        result = service.generate_audio(settings.to_request("Xin chào từ VieNeu phiên bản ba."))
    assert Path(result.audio_path).is_file()
    assert sf.info(result.audio_path).samplerate == 48000
    assert bool(coordinator.requests[0][0].reference_audio_id) == clone



def test_only_v3_factory_is_wrapped_not_legacy_ngoc_huyen():
    from omni_tts_core.engines.vieneu_engine import VieneuSubprocessEngine

    descriptor = provider_descriptor("vieneu")
    registry = ModelRegistry()
    for model_id in ("vieneu_v3_turbo", "vieneu_v2_standard"):
        router = descriptor.engine_factory(registry.get(model_id), None)
        try:
            assert isinstance(router, VieneuRoutingEngine if model_id == "vieneu_v3_turbo" else VieneuSubprocessEngine)
        finally:
            router.close()


def test_archive_with_traversal_or_wrong_sample_rate_is_rejected(tmp_path):
    from omni_tts_core.engines.vieneu_routing_engine import _read_batch

    archive_path = tmp_path / "result.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.wav", b"bad")
    with pytest.raises(GenerationError):
        _read_batch(archive_path, 1, tmp_path, 0)
