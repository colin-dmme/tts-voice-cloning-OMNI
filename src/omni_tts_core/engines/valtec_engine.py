from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

import soundfile as sf

from omni_tts_core.engines.base import BaseTtsEngine, TtsEngineRequest, TtsEngineResult
from omni_tts_core.engines.subprocess_tools import run_worker_process
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.progress import check_cancel
from omni_tts_shared.errors import EngineDependencyError, GenerationError
from omni_tts_shared.valtec_voices import VALTEC_DEFAULT_SPEAKER, VALTEC_SPEAKERS


class ValtecSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.worker_dir = project_path("engines/valtec_worker")
        self.worker_script = self.worker_dir / "synthesize.py"

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        runtime = self._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="valtec_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            output_path = Path(temp_dir) / "output.wav"
            payload_path = Path(temp_dir) / "request.json"
            payload_path.write_text(
                json.dumps(self._payload(request, output_path), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            command = [str(runtime.python_path), str(self.worker_script), "--request", str(payload_path)]
            env = dict(os.environ)
            env.update({
                "HF_HOME": str(project_path(".hf_cache")),
                "HF_HUB_CACHE": str(project_path(".hf_cache/hub")),
                "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
                "LOCALAPPDATA": str(project_path(".hf_cache/valtec_appdata")),
            })
            if runtime.python_paths:
                env["PYTHONPATH"] = os.pathsep.join(str(path) for path in runtime.python_paths)
            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=900,
                    cancel_event=request.cancel_event,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("Valtec xử lý quá lâu và đã bị dừng.") from exc
            if completed.returncode != 0:
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"Valtec không sinh được audio: {message}")
            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("Valtec không tạo file WAV đầu ra.")
            audio, sample_rate = sf.read(str(output_path), dtype="float32")
            return TtsEngineResult(audio=audio, sample_rate=int(sample_rate))

    def _worker_runtime(self) -> "WorkerRuntime":
        portable_python = PROJECT_ROOT / "runtime" / "python" / "python.exe"
        portable_site = self.worker_dir / "site-packages"
        vendor_path = self.worker_dir / "vendor" / "valtec-tts"
        python_paths = [vendor_path] if vendor_path.exists() else []
        if portable_python.exists() and portable_site.exists():
            return WorkerRuntime(portable_python, [self.worker_dir, portable_site, *python_paths])
        candidates = [
            self.worker_dir / ".venv" / "Scripts" / "python.exe",
            self.worker_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return WorkerRuntime(candidate, python_paths)
        raise EngineDependencyError(
            "Valtec worker chưa được cài. Hãy chạy install_valtec_worker.bat trước."
        )

    def _payload(self, request: TtsEngineRequest, output_path: Path) -> dict:
        payload = {
            "text": request.text,
            "language": request.language,
            "output_path": str(output_path),
            "speaker": _speaker_id(request.speaker_id),
            "speed": request.speed,
        }
        if request.reference_audio_path:
            payload["ref_audio"] = str(request.reference_audio_path.resolve())
        return payload


def _clean_worker_error(message: str) -> str:
    if "No module named 'valtec_tts'" in message:
        return "Valtec worker thiếu valtec-tts. Chạy install_valtec_worker.bat."
    if "No module named 'torch'" in message:
        return "Valtec worker thiếu torch. Chạy install_valtec_worker.bat."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Không rõ lỗi từ worker."
    for line in reversed(lines):
        if line.startswith(("Valtec worker loi:", "ImportError:", "ModuleNotFoundError:", "RuntimeError:")):
            return line
    return lines[-1]


def _speaker_id(value: str | None) -> str:
    if value in VALTEC_SPEAKERS:
        return value
    return VALTEC_DEFAULT_SPEAKER


class WorkerRuntime(NamedTuple):
    python_path: Path
    python_paths: list[Path]
