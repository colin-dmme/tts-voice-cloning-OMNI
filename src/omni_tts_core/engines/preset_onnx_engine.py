from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import (
    BaseTtsEngine,
    BatchChunkCallback,
    BatchProgressCallback,
    TtsEngineRequest,
    TtsEngineResult,
)
from omni_tts_core.engines.batch_progress import report_ready_chunks
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_core.provider_options import (
    normalize_provider_options,
    provider_settings_for_model,
)
from omni_tts_core.text.punctuation_pauses import (
    PauseRange,
    PunctuationPauseConfig,
    split_with_punctuation_pauses,
)
from omni_tts_core.worker_installation import (
    portable_python_path,
    worker_for_spec,
    worker_site_packages,
    worker_venv_python,
)
from omni_tts_shared.errors import EngineDependencyError, GenerationError


class _JsonLineWorker:
    """Persistent isolated worker using the same protocol for preset ONNX TTS."""

    def __init__(self, worker_name: str, provider_label: str) -> None:
        self.worker_name = worker_name
        self.provider_label = provider_label
        self.worker_dir = project_path(f"engines/{worker_name}")
        self.worker_script = self.worker_dir / "synthesize.py"
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=3)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                process.kill()

    def run(self, payload: dict, *, timeout: float, cancel_event, tick_callback) -> None:
        with self._lock:
            process = self._ensure_process()
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
            responses: queue.Queue[str] = queue.Queue(maxsize=1)
            threading.Thread(
                target=lambda: responses.put(process.stdout.readline()), daemon=True
            ).start()
            deadline = time.monotonic() + timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    self.close()
                    check_cancel(cancel_event)
                if time.monotonic() >= deadline:
                    self.close()
                    raise GenerationError(
                        f"{self.provider_label} xử lý quá lâu và đã bị dừng."
                    )
                try:
                    line = responses.get(timeout=0.1)
                    break
                except queue.Empty:
                    tick_callback()
                    if process.poll() is not None:
                        error = process.stderr.read() if process.stderr else ""
                        self._process = None
                        raise GenerationError(
                            f"{self.provider_label} worker đã thoát: {_clean_error(error)}"
                        )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                self.close()
                raise GenerationError(
                    f"{self.provider_label} worker trả dữ liệu không hợp lệ."
                ) from exc
            if not response.get("ok"):
                raise GenerationError(
                    f"{self.provider_label} không sinh được audio: "
                    f"{response.get('error') or 'Không rõ lỗi.'}"
                )

    def _ensure_process(self) -> subprocess.Popen:
        if self._process is not None and self._process.poll() is None:
            return self._process
        if not self.worker_script.is_file():
            raise EngineDependencyError(
                f"Thiếu mã worker {self.provider_label}: {self.worker_script}"
            )
        python_path = worker_venv_python(self.worker_name)
        extra_paths: list[Path] = []
        if not python_path.exists():
            python_path = portable_python_path()
            site_packages = worker_site_packages(self.worker_name)
            if python_path.exists() and site_packages.exists():
                extra_paths = [self.worker_dir, site_packages]
        if not python_path.exists():
            raise EngineDependencyError(
                f"Worker {self.provider_label} chưa được cài. Mở Quản lý model, "
                "chọn model rồi bấm Cài worker/môi trường."
            )
        env = dict(os.environ)
        if extra_paths:
            current = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = os.pathsep.join(
                [*(str(path) for path in extra_paths), *([current] if current else [])]
            )
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            [str(python_path), str(self.worker_script), "--serve"],
            cwd=str(self.worker_dir),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        return self._process


class PresetOnnxSubprocessEngine(BaseTtsEngine):
    """Metadata-driven engine for fixed/preset voice ONNX providers."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        from omni_tts_core.provider_registry import provider_descriptor

        descriptor = provider_descriptor(spec.provider)
        if descriptor is None:
            raise GenerationError(f"Provider chưa được khai báo: {spec.provider}")
        worker_name = worker_for_spec(spec) or descriptor.worker_name
        if not worker_name:
            raise GenerationError(f"{descriptor.label} chưa khai báo worker.")
        self.descriptor = descriptor
        self.worker = _JsonLineWorker(worker_name, descriptor.label)

    def close(self) -> None:
        self.worker.close()

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
        options = normalize_provider_options(
            self.descriptor,
            requests[0].provider_options,
            settings=provider_settings_for_model(self.descriptor, self.spec.runtime),
        )
        outputs_root = PROJECT_ROOT / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f"{self.spec.provider}_", dir=outputs_root
        ) as temp_dir:
            temp_path = Path(temp_dir)
            chunks: list[dict] = []
            for index, request in enumerate(requests):
                chunk: dict = {
                    "text": request.text,
                    "output_path": str(temp_path / f"chunk_{index:04d}.wav"),
                }
                if request.punctuation_pause_enabled:
                    config = PunctuationPauseConfig(
                        sentence_ms=request.sentence_pause_ms,
                        comma_ms=request.comma_pause_ms,
                        clause_ms=request.clause_pause_ms,
                        ellipsis_ms=request.ellipsis_pause_ms,
                        sentence_range=_pause_range(request, "sentence"),
                        comma_range=_pause_range(request, "comma"),
                        clause_range=_pause_range(request, "clause"),
                        ellipsis_range=_pause_range(request, "ellipsis"),
                    )
                    chunk["segments"] = [
                        {"text": item.text, "pause_after_ms": item.pause_after_ms}
                        for item in split_with_punctuation_pauses(request.text, config)
                    ]
                chunks.append(chunk)
            payload = {
                "model_root": str(self.spec.local_path),
                "runtime": self.spec.runtime,
                "speaker_id": requests[0].speaker_id,
                "language": requests[0].language,
                "speed": requests[0].speed,
                "options": options,
                "chunks": chunks,
            }
            reported: set[int] = set()

            def report(force: bool = False) -> None:
                report_ready_chunks(
                    chunks, reported, progress_callback, chunk_callback, force=force
                )

            self.worker.run(
                payload,
                timeout=300 + 90 * len(chunks),
                cancel_event=requests[0].cancel_event,
                tick_callback=report,
            )
            check_cancel(requests[0].cancel_event)
            report(force=True)
            results: list[TtsEngineResult] = []
            for chunk in chunks:
                path = Path(chunk["output_path"])
                if not path.is_file():
                    raise GenerationError(
                        f"{self.descriptor.label} thiếu file đầu ra: {path.name}"
                    )
                audio, sample_rate = sf.read(str(path), dtype="float32")
                results.append(TtsEngineResult(audio=audio, sample_rate=int(sample_rate)))
            return results


def _pause_range(request: TtsEngineRequest, prefix: str) -> PauseRange | None:
    if not getattr(request, f"{prefix}_pause_random_enabled"):
        return None
    return PauseRange(
        getattr(request, f"{prefix}_pause_min_ms"),
        getattr(request, f"{prefix}_pause_max_ms"),
    )


def _clean_error(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    return lines[-1] if lines else "Không rõ lỗi từ worker."
