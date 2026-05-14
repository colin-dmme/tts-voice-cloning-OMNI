from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.subprocess_tools import run_worker_process
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import EngineDependencyError, GenerationError


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
