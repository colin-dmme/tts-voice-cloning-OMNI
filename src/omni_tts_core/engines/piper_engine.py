from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import atexit
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
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_core.text.punctuation_pauses import (
    PunctuationPauseConfig,
    split_with_punctuation_pauses,
)
from omni_tts_shared.errors import EngineDependencyError, GenerationError


class _SharedPiperWorker:
    """One worker process shared by every Piper voice in the application."""

    def __init__(self) -> None:
        self.worker_dir = project_path("engines/piper_worker")
        self.worker_script = self.worker_dir / "synthesize.py"
        self._process: subprocess.Popen | None = None
        self._process_lock = threading.Lock()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            process.kill()

    def run(
        self,
        runtime: "WorkerRuntime",
        payload: dict,
        *,
        timeout: float,
        cancel_event,
    ) -> None:
        with self._process_lock:
            process = self._ensure_process(runtime)
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
            response_queue: queue.Queue[str] = queue.Queue(maxsize=1)
            reader = threading.Thread(
                target=lambda: response_queue.put(process.stdout.readline()),
                daemon=True,
            )
            reader.start()
            deadline = time.monotonic() + timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    self.close()
                    check_cancel(cancel_event)
                if time.monotonic() >= deadline:
                    self.close()
                    raise GenerationError("Piper xử lý quá lâu và đã bị dừng.")
                try:
                    line = response_queue.get(timeout=0.1)
                    break
                except queue.Empty:
                    if process.poll() is not None:
                        stderr = process.stderr.read() if process.stderr is not None else ""
                        self._process = None
                        raise GenerationError(
                            f"Piper worker đã thoát: {_clean_worker_error(stderr)}"
                        )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                self.close()
                raise GenerationError(f"Piper worker trả dữ liệu không hợp lệ: {line}") from exc
            if not response.get("ok"):
                raise GenerationError(
                    f"Piper không sinh được audio: {response.get('error') or 'Không rõ lỗi.'}"
                )

    def _ensure_process(self, runtime: "WorkerRuntime") -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            [str(runtime.python_path), str(self.worker_script), "--serve"],
            cwd=str(self.worker_dir),
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        return self._process

    def _worker_runtime(self) -> "WorkerRuntime":
        portable_python = PROJECT_ROOT / "runtime" / "python" / "python.exe"
        portable_site = self.worker_dir / "site-packages"
        if portable_python.exists() and portable_site.exists():
            return WorkerRuntime(portable_python, [self.worker_dir, portable_site])
        for candidate in (
            self.worker_dir / ".venv" / "Scripts" / "python.exe",
            self.worker_dir / ".venv" / "bin" / "python",
        ):
            if candidate.exists():
                return WorkerRuntime(candidate, [])
        raise EngineDependencyError(
            "Piper worker chưa được cài. Mở Quản lý model, chọn giọng Piper rồi bấm "
            "Cài worker/môi trường."
        )


_SHARED_PIPER_WORKER = _SharedPiperWorker()
atexit.register(_SHARED_PIPER_WORKER.close)


class PiperSubprocessEngine(BaseTtsEngine):
    """Fast fixed-voice ONNX provider backed by one shared Piper worker."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

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
        runtime = _SHARED_PIPER_WORKER._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="piper_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            chunks = []
            for index, request in enumerate(requests):
                item = {
                    "text": request.text,
                    "output_path": str(temp_path / f"chunk_{index:03d}.wav"),
                }
                if request.punctuation_pause_enabled:
                    config = PunctuationPauseConfig(
                        sentence_ms=request.sentence_pause_ms,
                        comma_ms=request.comma_pause_ms,
                        clause_ms=request.clause_pause_ms,
                        ellipsis_ms=request.ellipsis_pause_ms,
                    )
                    item["segments"] = [
                        {
                            "text": segment.text,
                            "pause_after_ms": segment.pause_after_ms,
                        }
                        for segment in split_with_punctuation_pauses(request.text, config)
                    ]
                chunks.append(item)
            payload = {
                "model_path": str(self.spec.local_path / str(self.spec.runtime["model_file"])),
                "config_path": str(self.spec.local_path / str(self.spec.runtime["config_file"])),
                "speaker_id": requests[0].speaker_id,
                "speed": requests[0].speed,
                "sentence_pause_ms": (
                    requests[0].sentence_pause_ms
                    if requests[0].punctuation_pause_enabled
                    else 0
                ),
                "chunks": chunks,
            }
            _SHARED_PIPER_WORKER.run(
                runtime,
                payload,
                timeout=300 + 60 * len(chunks),
                cancel_event=requests[0].cancel_event,
            )
            check_cancel(requests[0].cancel_event)
            results: list[TtsEngineResult] = []
            for index, chunk in enumerate(chunks):
                output_path = Path(chunk["output_path"])
                if not output_path.exists():
                    raise GenerationError(f"Piper thiếu file đầu ra: {output_path.name}")
                audio, sample_rate = sf.read(str(output_path), dtype="float32")
                results.append(TtsEngineResult(audio=audio, sample_rate=int(sample_rate)))
                if chunk_callback is not None:
                    chunk_callback(index, output_path)
                if progress_callback is not None:
                    progress_callback(index + 1, len(chunks))
            return results


def _clean_worker_error(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    return lines[-1] if lines else "Không rõ lỗi từ worker."


class WorkerRuntime(NamedTuple):
    python_path: Path
    python_paths: list[Path]
