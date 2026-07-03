from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

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

if TYPE_CHECKING:
    from omni_tts_core.engine_profile_cache import EngineProfileCache


class VieneuSubprocessEngine(BaseTtsEngine):
    def __init__(self, spec: ModelSpec, cache: "EngineProfileCache | None" = None) -> None:
        self.spec = spec
        self._cache = cache
        self._device_policy = RuntimeDevicePolicy()
        self.worker_dir = project_path("engines/vieneu_worker")
        self.worker_script = self.worker_dir / "synthesize.py"
        self.encoder_script = self.worker_dir / "encode_reference.py"

    def generate(self, request: TtsEngineRequest) -> TtsEngineResult:
        runtime = self._worker_runtime()
        (PROJECT_ROOT / "outputs").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="vieneu_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "output.wav"
            payload_path = temp_path / "request.json"
            payload_path.write_text(
                json.dumps(
                    self._payload(request, output_path, scratch_dir=temp_path),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            command = [str(runtime.python_path), str(self.worker_script), "--request", str(payload_path)]
            env = _worker_env(runtime.python_paths)
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
                if completed.returncode == -1073741819:
                    raise GenerationError(_native_crash_message(completed.stderr.strip() or completed.stdout.strip()))
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"VieNeu không sinh được audio: {message}")
            check_cancel(request.cancel_event)
            if not output_path.exists():
                raise GenerationError("VieNeu không tạo file WAV đầu ra.")
            self._try_write_cache_meta(request)
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

        with tempfile.TemporaryDirectory(prefix="vieneu_batch_", dir=PROJECT_ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)

            chunks = []
            for index, req in enumerate(requests):
                out = temp_path / f"chunk_{index:03d}.wav"
                chunks.append({"text": req.text, "output_path": str(out)})

            base_payload = self._base_payload(first, scratch_dir=temp_path)
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

            try:
                completed = run_worker_process(
                    command,
                    cwd=str(self.worker_dir),
                    env=env,
                    timeout=900 + 300 * len(requests),
                    cancel_event=cancel_event,
                    tick_callback=report_ready_chunks,
                )
            except subprocess.TimeoutExpired as exc:
                raise GenerationError("VieNeu batch xử lý quá lâu và đã bị dừng.") from exc
            report_ready_chunks()

            if completed.returncode != 0:
                if completed.returncode == -1073741819:
                    raise GenerationError(_native_crash_message(completed.stderr.strip() or completed.stdout.strip()))
                message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
                raise GenerationError(f"VieNeu không sinh được audio (batch): {message}")

            check_cancel(cancel_event)
            self._try_write_cache_meta(first)

            results = []
            for chunk in chunks:
                out = Path(chunk["output_path"])
                if not out.exists():
                    raise GenerationError(f"VieNeu không tạo file WAV đầu ra cho chunk: {out.name}")
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
            "VieNeu worker chưa được cài. Mở tab Quản lý model, chọn model VieNeu rồi bấm Cài worker/môi trường."
        )

    def _base_payload(self, request: TtsEngineRequest, scratch_dir: Path | None = None) -> dict:
        mode = str(self.spec.runtime.get("vieneu_mode") or _mode_from_model_id(self.spec.model_id))
        payload: dict = {
            "mode": mode,
            "emotion": request.emotion or "natural",
            "speed": request.speed,
        }
        payload.update(_runtime_payload(self.spec.runtime))
        payload.update(self._device_policy.payload_for(self.spec, request.runtime_target, mode=mode))
        use_request_codec_for_generation = True
        if (
            mode == "standard"
            and self.spec.runtime.get("gguf_filename")
            and request.reference_audio_path is not None
        ):
            use_request_codec_for_generation = False
        if request.codec_repo and use_request_codec_for_generation:
            payload["codec_repo"] = request.codec_repo
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_k is not None:
            payload["top_k"] = request.top_k
        if request.reference_audio_path:
            ref_codes_path = self._standard_gguf_ref_codes_path(request, mode, scratch_dir)
            if ref_codes_path is not None:
                payload["ref_codes_path"] = str(ref_codes_path)
                payload["codec_repo"] = str(
                    self.spec.runtime.get("codec_repo")
                    or "neuphonic/neucodec-onnx-decoder-int8"
                )
                payload["codec_device"] = "cpu"
            else:
                payload["ref_audio"] = str(request.reference_audio_path)
        else:
            voice_name = request.speaker_id if request.speaker_id in self.spec.voice_presets else None
            if voice_name:
                payload["voice_name"] = voice_name
        if request.reference_text:
            payload["ref_text"] = request.reference_text
        if mode == "turbo" and request.cached_prompt_path is not None:
            payload["cached_prompt_path"] = str(request.cached_prompt_path)
        return payload

    def _standard_gguf_ref_codes_path(
        self,
        request: TtsEngineRequest,
        mode: str,
        scratch_dir: Path | None = None,
    ) -> Path | None:
        if (
            mode != "standard"
            or not self.spec.runtime.get("gguf_filename")
            or request.reference_audio_path is None
        ):
            return None
        cache_dir = request.cached_prompt_path
        if cache_dir is None:
            if scratch_dir is None:
                return None
            cache_dir = scratch_dir / "reference_codes"
        ref_codes_path = cache_dir / "ref_codes.npy"
        if ref_codes_path.exists():
            return ref_codes_path

        cache_dir.mkdir(parents=True, exist_ok=True)
        payload_path = cache_dir / "encode_request.json"
        encode_codec_repo = request.codec_repo
        if encode_codec_repo == "neuphonic/neucodec-onnx-decoder-int8":
            encode_codec_repo = None
        payload = {
            "ref_audio": str(request.reference_audio_path),
            "output_path": str(ref_codes_path),
            "codec_repo": encode_codec_repo or "neuphonic/distill-neucodec",
            "codec_device": "cpu",
        }
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        runtime = self._worker_runtime()
        env = _worker_env(runtime.python_paths)
        try:
            completed = run_worker_process(
                [str(runtime.python_path), str(self.encoder_script), "--request", str(payload_path)],
                cwd=str(self.worker_dir),
                env=env,
                timeout=600,
                cancel_event=request.cancel_event,
            )
        except subprocess.TimeoutExpired as exc:
            raise GenerationError("VieNeu encode profile quá lâu và đã bị dừng.") from exc
        if completed.returncode != 0:
            message = _clean_worker_error(completed.stderr.strip() or completed.stdout.strip())
            raise GenerationError(f"VieNeu không encode được Profile giọng: {message}")
        if not ref_codes_path.exists():
            raise GenerationError("VieNeu không tạo được ref_codes cho Profile giọng.")
        return ref_codes_path

    def _try_write_cache_meta(self, request: TtsEngineRequest) -> None:
        if (
            self._cache is None
            or request.cached_prompt_path is None
            or not request.reference_audio_path
        ):
            return
        cache_dir = request.cached_prompt_path
        if (cache_dir / "ref_codes.npy").exists() or (cache_dir / "ref_codes.pkl").exists():
            try:
                self._cache.write_meta(
                    cache_dir,
                    request.reference_audio_path,
                    request.reference_text or "",
                )
            except Exception:
                pass

    def _payload(
        self,
        request: TtsEngineRequest,
        output_path: Path,
        scratch_dir: Path | None = None,
    ) -> dict:
        payload = self._base_payload(request, scratch_dir=scratch_dir)
        payload["text"] = request.text
        payload["output_path"] = str(output_path)
        return payload


def _mode_from_model_id(model_id: str) -> str:
    if "turbo" in model_id:
        return "turbo"
    if "remote" in model_id:
        return "remote"
    if "pytorch" in model_id:
        return "pytorch"
    if "lora" in model_id:
        return "lora"
    return "standard"


def _runtime_payload(runtime: dict) -> dict:
    allowed = {
        "backbone_repo",
        "backbone_filename",
        "gguf_filename",
        "decoder_repo",
        "decoder_filename",
        "encoder_repo",
        "encoder_filename",
        "codec_repo",
        "codec_device",
        "backbone_device",
        "device",
        "prompt_format",
        "legacy_chat_format",
        "disable_emotion_tag",
        "temperature",
        "top_k",
        # pytorch mode
        "pytorch_device",
        # lora mode
        "lora_repo",
        "lora_filename",
        "base_repo",
    }
    return {key: value for key, value in runtime.items() if key in allowed and value not in ("", None)}


def _worker_env(python_paths: list[Path]) -> dict:
    env = dict(os.environ)
    env.update(hf_cache_env())
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in python_paths)
    return env


def _clean_worker_error(message: str) -> str:
    if (
        "Skipping import of cpp extensions due to incompatible torch version" in message
        and "Redirects are currently not supported" in message
    ):
        return (
            "Backend VieNeu bị crash native trên Windows. "
            "Nếu đang dùng Profile với Standard/GGUF, hãy thử xóa cache profile hoặc encode lại bằng NeuCodec Distill."
        )
    if "No module named 'neucodec'" in message:
        return "VieNeu Standard cần neucodec để clone giọng. Mở Quản lý model và bấm Cài worker/môi trường."
    if "No module named 'torch'" in message or "Torch is required" in message:
        return "VieNeu cần torch trong worker để clone giọng. Mở Quản lý model và bấm Cài worker/môi trường."
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Không rõ lỗi từ worker."
    for line in reversed(lines):
        if line.startswith(("VieNeu worker lỗi:", "ImportError:", "ModuleNotFoundError:", "RuntimeError:")):
            return line
        if "Standard CPU hiện không hỗ trợ clone" in line:
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


def _native_crash_message(message: str) -> str:
    detail = _clean_worker_error(message)
    return f"VieNeu worker bị crash native trên Windows: {detail}"


class WorkerRuntime(NamedTuple):
    python_path: Path
    python_paths: list[Path]
