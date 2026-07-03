from __future__ import annotations

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
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_core.runtime_devices import RuntimeDevicePolicy
from omni_tts_core.storage_paths import hf_cache_env
from omni_tts_shared.errors import EngineDependencyError, GenerationError


class ChatterboxSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self._device_policy = RuntimeDevicePolicy()
        self.worker_dir = project_path("engines/chatterbox_worker")
        self.worker_script = self.worker_dir / "synthesize.py"

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        runtime = self._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="chatterbox_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            output_path = Path(temp_dir) / "output.wav"
            payload_path = Path(temp_dir) / "request.json"
            payload_path.write_text(
                json.dumps(self._payload(request, output_path), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            command = [str(runtime.python_path), str(self.worker_script), "--request", str(payload_path)]
            env = _worker_env(runtime.python_paths)
            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=1200,
                    cancel_event=request.cancel_event,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Chatterbox Turbo xử lý quá lâu và đã bị dừng.") from exc
            if completed.returncode != 0:
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
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
        if len(requests) == 1:
            result = self.generate(requests[0])
            if progress_callback is not None:
                progress_callback(1, 1)
            return [result]

        runtime = self._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        first = requests[0]
        cancel_event = first.cancel_event

        with tempfile.TemporaryDirectory(prefix="chatterbox_batch_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            chunks = []
            for index, req in enumerate(requests):
                out = temp_path / f"chunk_{index:03d}.wav"
                chunks.append({"text": req.text, "output_path": str(out)})

            batch_payload = {**self._base_payload(first), "batch": True, "chunks": chunks}
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

            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=1200 + 300 * len(requests),
                    cancel_event=cancel_event,
                    tick_callback=report_ready_chunks,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Chatterbox Turbo batch xử lý quá lâu và đã bị dừng.") from exc
            report_ready_chunks()

            if completed.returncode != 0:
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"Chatterbox Turbo không sinh được audio (batch): {message}")

            check_cancel(cancel_event)
            results = []
            for chunk in chunks:
                out = Path(chunk["output_path"])
                if not out.exists():
                    raise GenerationError(f"Chatterbox Turbo không tạo file WAV đầu ra cho chunk: {out.name}")
                audio, sample_rate = sf.read(str(out), dtype="float32")
                results.append(TtsEngineResult(audio=audio, sample_rate=int(sample_rate)))
            return results

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
            "Chatterbox worker chưa được cài. Hãy chạy install_chatterbox_worker.bat "
            "hoặc install_chatterbox_worker_cuda.bat trước."
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
        return "Chatterbox worker thiếu chatterbox-tts. Chạy install_chatterbox_worker.bat."
    if "No module named 'torch'" in message:
        return "Chatterbox worker thiếu torch. Chạy install_chatterbox_worker.bat."
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


def _audio_file_ready(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        if time.time() - path.stat().st_mtime < 0.2:
            return False
        return sf.info(str(path)).frames > 0
    except Exception:
        return False


class WorkerRuntime(NamedTuple):
    python_path: Path
    python_paths: list[Path]
