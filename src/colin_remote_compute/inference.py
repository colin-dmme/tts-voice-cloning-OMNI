"""Remote TTS execution shared by Studio routing and managed Colab jobs."""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import GenerationError

from .broker.client import BrokerClient
from .broker.failover import ConfirmSwitch, RemoteComputeCoordinator
from .broker.models import BrokerConnectionOptions, RemoteTtsRequest, WorkerProfile
from .broker.profiles import WorkerProfileDocument
from .inference_units import InferenceUnit, execute_units


def generate_vieneu(engine, requests, progress_callback=None, chunk_callback=None):
    from .context import managed_execution

    if not requests:
        return []
    if engine.spec.model_id != "vieneu_v3_turbo" or any(request.runtime_target != "remote" for request in requests):
        raise GenerationError("Colab VieNeu chỉ hỗ trợ v3 Turbo và không trộn local/remote trong một batch.")
    context = managed_execution()
    coordinator = context if context is not None else engine.coordinator_factory(
        engine.profile_store.load(), confirm_switch=engine.confirm_switch,
        status_callback=requests[0].status_callback,
    )
    job_id = context.next_call_id() if context is not None else uuid.uuid4().hex
    batch_size = max(1, min(16, int(engine.spec.runtime.get("remote_batch_size", 4))))
    if context is not None and getattr(context.lifecycle, "is_cpu_pool", False):
        batch_size = 1
    reference_cache: dict[Path, bytes] = {}
    prepared = []
    for request in requests:
        check_cancel(request.cancel_event)
        reference = None
        if request.reference_audio_path:
            path = request.reference_audio_path.resolve()
            if path not in reference_cache:
                reference_cache[path] = _reference_wave(path)
            reference = reference_cache[path]
        options = {
            key: engine.spec.runtime.get(key, default)
            for key, default in (("temperature", 0.8), ("top_k", 25), ("repetition_window", 64), ("denoise_reference", True))
        }
        options.update(request.provider_options or {})
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_k is not None:
            options["top_k"] = request.top_k
        asset_id = hashlib.sha256(reference).hexdigest() if reference is not None else None
        speaker_id = None if reference is not None else (request.speaker_id or engine.spec.default_voice_preset)
        key = json.dumps((asset_id, speaker_id, request.language, options), sort_keys=True, ensure_ascii=False)
        prepared.append((request, reference, asset_id, speaker_id, options, key))

    outputs = PROJECT_ROOT / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="vieneu-remote-", dir=outputs) as folder:
        root = Path(folder)
        def units():
            offset = 0
            while offset < len(prepared):
                first = prepared[offset]
                batch = [first]
                for item in prepared[offset + 1:offset + batch_size]:
                    if item[-1] != first[-1]:
                        break
                    batch.append(item)
                request, reference, asset_id, speaker_id, options, _key = first
                check_cancel(request.cancel_event)
                unit_id = f"batch-{offset + 1:04d}"
                remote = RemoteTtsRequest(
                    client_job_id=job_id, inference_unit_id=unit_id, idempotency_key=f"{job_id}:{unit_id}",
                    model_id="vieneu_v3_turbo", text=request.text, language=request.language,
                    batch_texts=tuple(item[0].text for item in batch), speaker_id=speaker_id,
                    reference_audio_id=asset_id, provider_options=options,
                    metadata={"runtime_target": "remote"},
                )
                yield InferenceUnit(remote, root / f"{unit_id}.zip", request.cancel_event, reference)
                offset += len(batch)

        for unit in execute_units(coordinator, units()):
            check_cancel(unit.cancel_event)
            paths = _read_batch(unit.destination, len(unit.request.batch_texts), root, len(results))
            for path in paths:
                check_cancel(unit.cancel_event)
                audio, rate = sf.read(path, dtype="float32")
                results.append(TtsEngineResult(audio=audio, sample_rate=rate))
                index = len(results)
                if chunk_callback is not None:
                    chunk_callback(index, path)
                if progress_callback is not None:
                    progress_callback(index, len(requests))
    return results


def generate_zerotts(engine, requests, progress_callback=None, chunk_callback=None):
    from .context import managed_execution

    if not requests:
        return []
    if any(request.runtime_target != "remote" for request in requests):
        raise GenerationError("Không được trộn local và remote trong cùng một batch.")
    context = managed_execution()
    coordinator = context if context is not None else engine.coordinator_factory(
        engine.profile_store.load(),
        confirm_switch=engine.confirm_switch,
        status_callback=requests[0].status_callback,
    )
    client_job_id = context.next_call_id() if context is not None else uuid.uuid4().hex
    results: list[TtsEngineResult] = []
    outputs_root = PROJECT_ROOT / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zerotts-remote-", dir=outputs_root) as folder:
        root = Path(folder)
        total = len(requests)
        def units():
            for index, engine_request in enumerate(requests, start=1):
                check_cancel(engine_request.cancel_event)
                inference_unit_id = f"chunk-{index:04d}"
                remote = RemoteTtsRequest(
                    client_job_id=client_job_id,
                    inference_unit_id=inference_unit_id,
                    idempotency_key=f"{client_job_id}:{inference_unit_id}",
                    model_id=engine.spec.model_id,
                    text=engine_request.text,
                    language=engine_request.language,
                    speaker_id=engine_request.speaker_id,
                    provider_options=dict(engine_request.provider_options or {}),
                    metadata={"runtime_target": "remote"},
                )
                yield InferenceUnit(remote, root / f"chunk_{index:04d}.wav", engine_request.cancel_event)

        for index, unit in enumerate(execute_units(coordinator, units()), 1):
            check_cancel(unit.cancel_event)
            destination = unit.destination
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


def _reference_wave(path: Path) -> bytes:
    try:
        with sf.SoundFile(path) as source:
            rate = source.samplerate
            duration = len(source) / rate
            if not 0.1 <= duration <= 30 or not 8000 <= rate <= 384000:
                raise GenerationError("Audio mẫu clone qua Colab cần dài 0,1..30 giây, nên dùng giọng sạch 3..15 giây.")
            audio = source.read(dtype="float32", always_2d=True).mean(axis=1)
        if not np.isfinite(audio).all():
            raise GenerationError("Audio mẫu chứa dữ liệu không hợp lệ.")
        stream = io.BytesIO()
        sf.write(stream, audio, rate, format="WAV", subtype="PCM_16")
        if stream.tell() > 10 * 1024 * 1024:
            raise GenerationError("Audio mẫu sau chuyển WAV vượt 10 MiB.")
        return stream.getvalue()
    except (OSError, RuntimeError) as error:
        raise GenerationError(f"Không đọc được audio mẫu: {path.name}") from error


def _read_batch(path: Path, count: int, root: Path, offset: int) -> list[Path]:
    try:
        with zipfile.ZipFile(path) as archive:
            expected = [f"chunk_{index:04d}.wav" for index in range(1, count + 1)]
            if sorted(archive.namelist()) != expected or sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise GenerationError("Kết quả batch VieNeu không khớp số đoạn hoặc vượt 100 MiB.")
            paths = []
            for index, name in enumerate(expected, start=offset + 1):
                audio = archive.read(name)
                info = sf.info(io.BytesIO(audio))
                if info.samplerate != 48000 or info.channels != 1 or info.frames <= 0:
                    raise GenerationError("Kết quả VieNeu phải là audio mono 48 kHz có nội dung.")
                destination = root / f"chunk_{index:04d}.wav"
                destination.write_bytes(audio)
                paths.append(destination)
            return paths
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        raise GenerationError("Không đọc được archive kết quả VieNeu từ Colab.") from error
