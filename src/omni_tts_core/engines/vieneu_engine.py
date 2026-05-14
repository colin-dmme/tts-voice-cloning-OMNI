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


class VieneuSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.worker_dir = project_path("engines/vieneu_worker")
        self.worker_script = self.worker_dir / "synthesize.py"

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        python_path = self._worker_python()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="vieneu_", dir=PROJECT_ROOT / "outputs") as temp_dir:
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
                    timeout=900,
                    cancel_event=request.cancel_event,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("VieNeu xử lý quá lâu và đã bị dừng.") from exc
            if completed.returncode != 0:
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"VieNeu không sinh được audio: {message}")
            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("VieNeu không tạo file WAV đầu ra.")
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
            "VieNeu worker chưa được cài. Hãy chạy install_vieneu_worker.bat trước."
        )

    def _payload(self, request: TtsEngineRequest, output_path: Path) -> dict:
        mode = _mode_from_model_id(self.spec.model_id)
        payload = {
            "text": request.text,
            "output_path": str(output_path),
            "mode": mode,
            "emotion": request.emotion or "natural",
            "speed": request.speed,
        }
        if request.reference_audio_path:
            payload["ref_audio"] = str(request.reference_audio_path)
        if request.reference_text:
            payload["ref_text"] = request.reference_text
        return payload


def _mode_from_model_id(model_id: str) -> str:
    if "turbo" in model_id:
        return "turbo"
    if "remote" in model_id:
        return "remote"
    return "standard"


def _clean_worker_error(message: str) -> str:
    if "No module named 'neucodec'" in message:
        return "VieNeu Standard cần neucodec để clone giọng. Chạy install_vieneu_worker.bat."
    if "No module named 'torch'" in message or "Torch is required" in message:
        return "VieNeu cần torch trong worker để clone giọng. Chạy install_vieneu_worker.bat."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Không rõ lỗi từ worker."
    for line in reversed(lines):
        if line.startswith(("VieNeu worker lỗi:", "ImportError:", "ModuleNotFoundError:", "RuntimeError:")):
            return line
        if "Standard CPU hiện không hỗ trợ clone" in line:
            return line
    return lines[-1]
