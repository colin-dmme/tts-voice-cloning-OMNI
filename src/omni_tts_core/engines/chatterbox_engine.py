from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

import soundfile as sf

from omni_tts_core.engines.base import (
    BaseTtsEngine,
    BatchChunkCallback,
    BatchProgressCallback,
    TtsEngineRequest,
    TtsEngineResult,
)
from omni_tts_core.engines.subprocess_tools import run_worker_process
from omni_tts_core.gpu_safety import (
    GpuSafetyConfig,
    GpuSafetyGuard,
    append_gpu_event,
    is_fatal_cuda_error,
)
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_core.runtime_devices import RuntimeDevicePolicy
from omni_tts_core.storage_paths import hf_cache_env
from omni_tts_shared.errors import EngineDependencyError, GenerationError, GpuSafetyError


class ChatterboxSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec, gpu_guard: GpuSafetyGuard | None = None) -> None:
        self.spec = spec
        self._device_policy = RuntimeDevicePolicy()
        self.worker_dir = project_path("engines/chatterbox_worker")
        self.worker_script = self.worker_dir / "synthesize.py"
        self._gpu_guard = gpu_guard or GpuSafetyGuard(GpuSafetyConfig.from_runtime(spec.runtime))

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        runtime = self._worker_runtime()
        gpu_guard = self._gpu_guard_for(request)
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="chatterbox_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            output_path = Path(temp_dir) / "output.wav"
            payload_path = Path(temp_dir) / "request.json"
            payload = self._payload(request, output_path)
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            use_gpu_guard = payload.get("device") == "cuda"
            if use_gpu_guard:
                gpu_guard.wait_until_safe(request.cancel_event, request.status_callback)
            command = [str(runtime.python_path), str(self.worker_script), "--request", str(payload_path)]
            env = _worker_env(runtime.python_paths)
            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=1200,
                    cancel_event=request.cancel_event,
                    supervisor_callback=(
                        lambda control: gpu_guard.check_runtime_with_cooldown(
                            control,
                            request.cancel_event,
                            request.status_callback,
                        )
                        if use_gpu_guard
                        else None
                    ),
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Chatterbox Turbo xử lý quá lâu và đã bị dừng.") from exc
            if completed.returncode != 0:
                raw_message = completed.stderr.strip() or completed.stdout.strip()
                message = _clean_worker_error(raw_message)
                if use_gpu_guard:
                    gpu_guard.record_worker_failure(raw_message or message)
                if is_fatal_cuda_error(message):
                    raise GpuSafetyError(_fatal_cuda_message(message))
                raise GenerationError(f"Chatterbox Turbo không sinh được audio: {message}")
            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("Chatterbox Turbo không tạo file WAV đầu ra.")
            audio, sample_rate = sf.read(str(output_path), dtype="float32")
            return TtsEngineResult(audio=audio, sample_rate=int(sample_rate))

    def generate_batch(
        self,
        requests: list[TtsEngineRequest],
        progress_callback: BatchProgressCallback | None = None,
        chunk_callback: BatchChunkCallback | None = None,
    ) -> list[TtsEngineResult]:
        if not requests:
            return []

        runtime = self._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        first = requests[0]
        gpu_guard = self._gpu_guard_for(first)
        cancel_event = first.cancel_event
        base_payload = self._base_payload(first)
        use_gpu_guard = base_payload.get("device") == "cuda"
        checkpoint_dir = _checkpoint_dir(self.spec, base_payload, requests)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="chatterbox_batch_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            chunks = []
            for index, req in enumerate(requests):
                out = checkpoint_dir / f"chunk_{index:05d}.wav"
                if out.exists() and not _audio_file_ready(out, minimum_age_seconds=0.0):
                    out.unlink(missing_ok=True)
                chunks.append({"text": req.text, "output_path": str(out)})

            batch_payload = {**base_payload, "batch": True, "chunks": chunks}
            payload_path = temp_path / "request.json"
            payload_path.write_text(
                json.dumps(batch_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            command = [str(runtime.python_path), str(self.worker_script), "--request", str(payload_path)]
            env = _worker_env(runtime.python_paths)
            reported_chunks: set[int] = set()

            def report_ready_chunks() -> None:
                _report_ready_chunks(chunks, reported_chunks, progress_callback, chunk_callback)

            report_ready_chunks()
            if reported_chunks and first.status_callback is not None:
                first.status_callback(
                    f"Tiếp tục từ checkpoint: đã có {len(reported_chunks)}/{len(chunks)} đoạn."
                )
            if len(reported_chunks) == len(chunks):
                return _read_checkpoint_results(chunks)
            if use_gpu_guard:
                gpu_guard.wait_until_safe(cancel_event, first.status_callback)

            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=1200 + 300 * len(requests),
                    cancel_event=cancel_event,
                    tick_callback=report_ready_chunks,
                    supervisor_callback=(
                        lambda control: gpu_guard.check_runtime_with_cooldown(
                            control,
                            cancel_event,
                            first.status_callback,
                        )
                        if use_gpu_guard
                        else None
                    ),
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Chatterbox Turbo batch xử lý quá lâu và đã bị dừng.") from exc
            report_ready_chunks()

            if completed.returncode != 0:
                raw_message = completed.stderr.strip() or completed.stdout.strip()
                message = _clean_worker_error(raw_message)
                if use_gpu_guard:
                    gpu_guard.record_worker_failure(raw_message or message)
                if is_fatal_cuda_error(message):
                    raise GpuSafetyError(_fatal_cuda_message(message))
                raise GenerationError(f"Chatterbox Turbo không sinh được audio (batch): {message}")

            check_cancel(cancel_event)
            results = []
            for chunk in chunks:
                out = Path(chunk["output_path"])
                if not out.exists():
                    raise GenerationError(f"Chatterbox Turbo không tạo file WAV đầu ra cho chunk: {out.name}")
                audio, sample_rate = sf.read(str(out), dtype="float32")
                results.append(TtsEngineResult(audio=audio, sample_rate=int(sample_rate)))
            append_gpu_event(
                gpu_guard.log_path,
                "checkpoint-complete",
                details={"checkpoint_dir": str(checkpoint_dir), "chunk_count": len(chunks)},
            )
            return results

    def _gpu_guard_for(self, request: TtsEngineRequest) -> GpuSafetyGuard:
        overrides = {
            "gpu_safety_enabled": request.gpu_safety_enabled,
            "gpu_start_temperature_c": request.gpu_start_temperature_c,
            "gpu_abort_temperature_c": request.gpu_abort_temperature_c,
            "gpu_abort_temperature_sustain_seconds": request.gpu_abort_temperature_sustain_seconds,
            "gpu_emergency_temperature_c": request.gpu_emergency_temperature_c,
            "gpu_cooldown_max_wait_seconds": request.gpu_cooldown_max_wait_seconds,
            "gpu_resume_temperature_c": request.gpu_resume_temperature_c,
            "gpu_minimum_free_vram_mb": request.gpu_minimum_free_vram_mb,
            "gpu_runtime_minimum_free_vram_mb": request.gpu_runtime_minimum_free_vram_mb,
            "gpu_maximum_utilization_percent": request.gpu_maximum_utilization_percent,
            "gpu_maximum_encoder_utilization_percent": request.gpu_maximum_encoder_utilization_percent,
        }
        self._gpu_guard.config = GpuSafetyConfig.from_runtime(self.spec.runtime, overrides)
        return self._gpu_guard

    def _worker_runtime(self) -> "WorkerRuntime":
        portable_python = PROJECT_ROOT / "runtime" / "python" / "python.exe"
        portable_site = self.worker_dir / "site-packages"
        if portable_python.exists() and portable_site.exists():
            return WorkerRuntime(portable_python, [self.worker_dir, portable_site])
        candidates = [
            self.worker_dir / ".venv" / "Scripts" / "python.exe",
            self.worker_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return WorkerRuntime(candidate, [])
        raise EngineDependencyError(
            "Chatterbox worker chưa được cài. Mở tab Quản lý model, chọn model Chatterbox rồi bấm Cài worker/môi trường."
        )

    def _base_payload(self, request: TtsEngineRequest) -> dict:
        runtime = self.spec.runtime
        payload: dict = {
            "language": request.language,
            "hf_repo": self.spec.hf_repo,
            "model_path": str(self.spec.local_path),
            "temperature": request.chatterbox_temperature
            if request.chatterbox_temperature is not None
            else float(_runtime_default(runtime, "chatterbox_temperature", 0.8)),
            "top_p": request.chatterbox_top_p
            if request.chatterbox_top_p is not None
            else float(_runtime_default(runtime, "chatterbox_top_p", 0.95)),
            "top_k": request.chatterbox_top_k
            if request.chatterbox_top_k is not None
            else int(_runtime_default(runtime, "chatterbox_top_k", 1000)),
            "repetition_penalty": request.chatterbox_repetition_penalty
            if request.chatterbox_repetition_penalty is not None
            else float(_runtime_default(runtime, "chatterbox_repetition_penalty", 1.2)),
            "norm_loudness": bool(request.chatterbox_norm_loudness),
        }
        if request.reference_audio_path:
            payload["ref_audio"] = str(request.reference_audio_path)
        if request.chatterbox_seed is not None:
            payload["seed"] = request.chatterbox_seed
        payload.update(self._device_policy.payload_for(self.spec, request.runtime_target))
        return payload

    def _payload(self, request: TtsEngineRequest, output_path: Path) -> dict:
        payload = self._base_payload(request)
        payload["text"] = request.text
        payload["output_path"] = str(output_path)
        return payload


def _runtime_default(runtime: dict, key: str, fallback):
    value = runtime.get(key)
    return fallback if value is None else value


def _worker_env(python_paths: list[Path]) -> dict[str, str]:
    env = dict(os.environ)
    env.update(hf_cache_env())
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    return env


def _clean_worker_error(message: str) -> str:
    if "No module named 'chatterbox'" in message:
        return "Chatterbox worker thiếu chatterbox-tts. Mở Quản lý model và bấm Cài worker/môi trường."
    if "No module named 'torch'" in message:
        return "Chatterbox worker thiếu torch. Mở Quản lý model và bấm Cài worker/môi trường."
    if "Audio prompt must be longer than 5 seconds" in message:
        return "Chatterbox Turbo cần audio mẫu dài hơn 5 giây để clone voice."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Không rõ lỗi từ worker."
    for line in reversed(lines):
        if line.startswith(("Chatterbox worker loi:", "ImportError:", "ModuleNotFoundError:", "RuntimeError:")):
            return line
    return lines[-1]


def _report_ready_chunks(
    chunks: list[dict],
    reported_chunks: set[int],
    progress_callback: BatchProgressCallback | None,
    chunk_callback: BatchChunkCallback | None,
) -> None:
    before = len(reported_chunks)
    for index, chunk in enumerate(chunks):
        if index in reported_chunks:
            continue
        out = Path(chunk["output_path"])
        if not _audio_file_ready(out):
            continue
        reported_chunks.add(index)
        if chunk_callback is not None:
            chunk_callback(index, out)
    if progress_callback is not None and len(reported_chunks) != before:
        progress_callback(len(reported_chunks), len(chunks))


def _audio_file_ready(path: Path, minimum_age_seconds: float = 0.2) -> bool:
    if not path.exists():
        return False
    try:
        if time.time() - path.stat().st_mtime < minimum_age_seconds:
            return False
        return sf.info(str(path)).frames > 0
    except Exception:
        return False


class WorkerRuntime(NamedTuple):
    python_path: Path
    python_paths: list[Path]


def _checkpoint_dir(
    spec: ModelSpec,
    base_payload: dict,
    requests: list[TtsEngineRequest],
) -> Path:
    ref_audio = Path(str(base_payload.get("ref_audio") or ""))
    try:
        ref_stat = ref_audio.stat()
        ref_signature = f"{ref_stat.st_size}:{ref_stat.st_mtime_ns}"
    except OSError:
        ref_signature = ""
    identity = {
        "schema": 1,
        "model_id": spec.model_id,
        "payload": base_payload,
        "reference_signature": ref_signature,
        "texts": [request.text for request in requests],
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return PROJECT_ROOT / "outputs" / "checkpoints" / "chatterbox" / digest


def _read_checkpoint_results(chunks: list[dict]) -> list[TtsEngineResult]:
    results = []
    for chunk in chunks:
        audio, sample_rate = sf.read(str(chunk["output_path"]), dtype="float32")
        results.append(TtsEngineResult(audio=audio, sample_rate=int(sample_rate)))
    return results


def _fatal_cuda_message(message: str) -> str:
    return (
        "GPU/CUDA đã mất trạng thái an toàn. Colin TTS đã dừng toàn bộ hàng đợi để tránh lỗi lan rộng "
        "hoặc làm màn hình mất tín hiệu. Các chunk hoàn thành đã được giữ để chạy tiếp. "
        f"Lỗi gốc: {message}"
    )
