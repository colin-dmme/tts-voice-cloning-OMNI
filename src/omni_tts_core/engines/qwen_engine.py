from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.subprocess_tools import run_worker_process
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import EngineDependencyError, GenerationError

logger = logging.getLogger(__name__)

# Windows: hide subprocess console windows
_POPEN_EXTRA: dict = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = subprocess.CREATE_NO_WINDOW


# ===================================================================
# Persistent Worker Engine — model loaded once, kept alive
# ===================================================================


class QwenPersistentEngine(BaseTtsEngine):
    """
    Qwen3-TTS engine using a persistent worker subprocess.

    The worker process starts once, loads the model into GPU memory,
    and stays alive to process requests via JSON-lines over stdin/stdout.
    Voice clone prompts are cached inside the worker.

    This is 10-20x faster than QwenSubprocessEngine for batch jobs
    because it avoids re-loading the model for every request.
    """

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.worker_dir = project_path("engines/qwen_worker")
        self.worker_script = self.worker_dir / "persistent_worker.py"
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        check_cancel(request.cancel_event)
        self._ensure_worker_running()
        check_cancel(request.cancel_event)

        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qwen_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            output_path = Path(temp_dir) / "output.wav"
            payload = self._build_payload(request, output_path)

            response = self._send_request(payload, cancel_event=request.cancel_event)

            if not response.get("ok"):
                error = response.get("error", "Unknown worker error")
                raise GenerationError(f"Qwen3-TTS không sinh được audio: {error}")

            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("Qwen3-TTS không tạo file WAV đầu ra.")

            audio, sample_rate = sf.read(str(output_path), dtype="float32")
            return TtsEngineResult(audio=audio, sample_rate=int(sample_rate))

    def shutdown(self) -> None:
        """Shut down the persistent worker process."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                try:
                    self._write_json({"action": "shutdown"})
                    self._process.wait(timeout=10)
                except Exception:
                    self._process.kill()
                    self._process.wait()
                finally:
                    self._process = None
                    logger.info("Qwen persistent worker shut down")

    # ------ internal ------

    def _ensure_worker_running(self) -> None:
        """Start the worker if not already running."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return  # already running

            python_path = self._worker_python()
            env = dict(os.environ)
            env.update({
                "HF_HOME": str(project_path(".hf_cache")),
                "HF_HUB_CACHE": str(project_path(".hf_cache/hub")),
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
            })

            logger.info("Starting Qwen persistent worker...")
            self._process = subprocess.Popen(
                [str(python_path), str(self.worker_script)],
                cwd=str(self.worker_dir),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
                **_POPEN_EXTRA,
            )

            # Read the "ready" signal
            ready_line = self._process.stdout.readline().strip()
            if not ready_line:
                stderr_out = self._process.stderr.read(2000)
                raise EngineDependencyError(
                    f"Qwen worker không phản hồi. Stderr: {stderr_out}"
                )
            try:
                ready = json.loads(ready_line)
                if ready.get("status") != "ready":
                    raise EngineDependencyError(f"Worker phản hồi bất thường: {ready_line}")
            except json.JSONDecodeError:
                raise EngineDependencyError(f"Worker phản hồi lỗi: {ready_line}")

            # Start a background thread to drain stderr (prevents pipe buffer deadlock)
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, daemon=True
            )
            self._stderr_thread.start()

            logger.info("Qwen persistent worker is ready")

    def _drain_stderr(self) -> None:
        """Read stderr in background, logging worker messages."""
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    logger.info(f"[qwen-worker] {line}")
        except Exception:
            pass

    def _send_request(self, payload: dict, cancel_event=None, timeout: float = 1200) -> dict:
        """Send a JSON request and wait for JSON response."""
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                raise GenerationError("Qwen worker đã dừng bất ngờ.")
            self._write_json(payload)

        # Wait for response (outside lock so cancel can work)
        started_at = time.monotonic()
        while True:
            if cancel_event and cancel_event.is_set():
                raise GenerationError("Đã huỷ request.")

            # Check if process died
            if self._process.poll() is not None:
                raise GenerationError("Qwen worker đã dừng bất ngờ.")

            # Try reading with a small timeout using select-like approach
            # Since we're on Windows, use a polling approach
            try:
                line = self._process.stdout.readline()
                if line.strip():
                    return json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if time.monotonic() - started_at > timeout:
                self.shutdown()
                raise GenerationError("Qwen3-TTS xử lý quá lâu.")

    def _write_json(self, data: dict) -> None:
        """Write a JSON line to worker stdin."""
        self._process.stdin.write(json.dumps(data, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

    def _build_payload(self, request: TtsEngineRequest, output_path: Path) -> dict:
        payload = {
            "action": "generate",
            "text": request.text,
            "language": request.language,
            "output_path": str(output_path),
            "hf_repo": self.spec.hf_repo,
            "model_path": str(self.spec.local_path),
        }
        if request.reference_audio_path:
            payload["ref_audio"] = str(request.reference_audio_path)
        if request.reference_text:
            payload["ref_text"] = request.reference_text
        return payload

    def _worker_python(self) -> Path:
        candidates = [
            self.worker_dir / ".venv" / "Scripts" / "python.exe",
            self.worker_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise EngineDependencyError(
            "Qwen worker chưa được cài. Hãy chạy install_qwen_worker.bat trước."
        )


# ===================================================================
# Subprocess Engine (legacy) — kept for backward compatibility
# ===================================================================


class QwenSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.worker_dir = project_path("engines/qwen_worker")
        self.worker_script = self.worker_dir / "synthesize.py"

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        python_path = self._worker_python()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qwen_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            output_path = Path(temp_dir) / "output.wav"
            payload_path = Path(temp_dir) / "request.json"
            payload_path.write_text(
                json.dumps(self._payload(request, output_path), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            command = [str(python_path), str(self.worker_script), "--request", str(payload_path)]
            env = dict(os.environ)
            env.update({
                "HF_HOME": str(project_path(".hf_cache")),
                "HF_HUB_CACHE": str(project_path(".hf_cache/hub")),
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
            })
            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=1200,
                    cancel_event=request.cancel_event,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Qwen3-TTS xử lý quá lâu và đã bị dừng.") from exc
            if completed.returncode != 0:
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"Qwen3-TTS không sinh được audio: {message}")
            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("Qwen3-TTS không tạo file WAV đầu ra.")
            audio, sample_rate = sf.read(str(output_path), dtype="float32")
            return TtsEngineResult(audio=audio, sample_rate=int(sample_rate))

    def _worker_python(self) -> Path:
        candidates = [
            self.worker_dir / ".venv" / "Scripts" / "python.exe",
            self.worker_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise EngineDependencyError(
            "Qwen worker chưa được cài. Hãy chạy install_qwen_worker.bat trước."
        )

    @staticmethod
    def is_worker_ready() -> bool:
        """Check if the Qwen worker has all required dependencies."""
        worker_dir = project_path("engines/qwen_worker")
        python_candidates = [
            worker_dir / ".venv" / "Scripts" / "python.exe",
            worker_dir / ".venv" / "bin" / "python",
        ]
        python_path = None
        for c in python_candidates:
            if c.exists():
                python_path = c
                break
        if python_path is None:
            return False

        try:
            result = subprocess.run(
                [str(python_path), "-c", "import torch; import qwen_tts"],
                capture_output=True, timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def ensure_worker_ready(log_callback=None) -> bool:
        """
        Ensure the Qwen worker environment is set up with torch and qwen-tts.
        Returns True if worker is ready, raises on failure.
        """
        if QwenSubprocessEngine.is_worker_ready():
            return True

        worker_dir = project_path("engines/qwen_worker")
        if not worker_dir.exists():
            raise EngineDependencyError(
                f"Thư mục worker không tồn tại: {worker_dir}"
            )

        if log_callback:
            log_callback("Đang cài đặt Qwen worker (torch + qwen-tts)...")

        env = dict(os.environ)
        env.update({
            "HF_HOME": str(project_path(".hf_cache")),
            "HF_HUB_CACHE": str(project_path(".hf_cache/hub")),
            "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
        })

        steps = [
            (["uv", "sync", "--inexact"], "Syncing worker dependencies..."),
            (["uv", "pip", "install", "qwen-tts"], "Installing qwen-tts..."),
            (["uv", "pip", "install", "torch", "--index-url",
              "https://download.pytorch.org/whl/cu126"], "Installing torch (CUDA 12.6)..."),
        ]

        for cmd, msg in steps:
            if log_callback:
                log_callback(msg)
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(worker_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                if result.returncode != 0:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    raise EngineDependencyError(
                        f"Lỗi cài Qwen worker khi chạy '{' '.join(cmd)}': {error_msg}"
                    )
            except subprocess.TimeoutExpired:
                raise EngineDependencyError("Cài Qwen worker quá lâu, đã dừng.")

        if not QwenSubprocessEngine.is_worker_ready():
            raise EngineDependencyError(
                "Cài xong nhưng worker vẫn chưa sẵn sàng. Thử chạy install_qwen_worker.bat."
            )

        if log_callback:
            log_callback("✅ Qwen worker đã sẵn sàng!")
        return True

    def _payload(self, request: TtsEngineRequest, output_path: Path) -> dict:
        payload = {
            "text": request.text,
            "language": request.language,
            "output_path": str(output_path),
            "hf_repo": self.spec.hf_repo,
            "model_path": str(self.spec.local_path),
            "speed": request.speed,
        }
        if request.reference_audio_path:
            payload["ref_audio"] = str(request.reference_audio_path)
        if request.reference_text:
            payload["ref_text"] = request.reference_text
        return payload


def _clean_worker_error(message: str) -> str:
    if "No module named 'qwen_tts'" in message:
        return "Qwen worker thiếu qwen-tts. Chạy install_qwen_worker.bat."
    if "No module named 'torch'" in message:
        return "Qwen worker thiếu torch. Chạy install_qwen_worker.bat."
    if "uu tien clone voice" in message:
        return "Qwen3-TTS Base cần Profile giọng để clone voice."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Không rõ lỗi từ worker."
    for line in reversed(lines):
        if line.startswith(("Qwen worker loi:", "ImportError:", "ModuleNotFoundError:", "RuntimeError:")):
            return line
    return lines[-1]
