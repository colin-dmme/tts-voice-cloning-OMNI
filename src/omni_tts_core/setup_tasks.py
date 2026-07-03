from __future__ import annotations

import shutil
from pathlib import Path

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_core.runtime_devices import configured_runtime_device
from omni_tts_core.runtime_status import RuntimeStatusService
from omni_tts_core.storage_paths import local_storage_config_path, storage_roots
from omni_tts_core.worker_installation import (
    base_installer_for_provider,
    gpu_installer_for_provider,
    host_gpu_summary,
    install_base_runtime,
    install_gpu_acceleration,
    provider_label,
    worker_for_provider,
    worker_install_path,
)
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import SetupTaskStatus


class SetupService:
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        storage: ModelStorage | None = None,
        runtime_status: RuntimeStatusService | None = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.storage = storage or ModelStorage(self.registry)
        self.runtime_status = runtime_status or RuntimeStatusService(self.registry, self.storage)

    def environment_statuses(self) -> list[SetupTaskStatus]:
        statuses = [
            _file_status(
                task_id="env:start",
                label="File mở app",
                path=PROJECT_ROOT / "Start-ColinTTS.bat",
                detail_ok="Dùng file này sau khi clone để chuẩn bị môi trường và mở app.",
                detail_missing="Thiếu Start-ColinTTS.bat; repo không đủ file khởi động.",
            ),
            _command_status(
                task_id="env:uv",
                label="uv",
                command="uv",
                detail_ok="Đã có uv để đồng bộ môi trường Python.",
                detail_missing="Chưa thấy uv. Start-ColinTTS.bat sẽ cố tự cài khi chạy.",
            ),
            _command_status(
                task_id="env:git",
                label="Git",
                command="git",
                detail_ok="Đã có Git để pull source/private repo.",
                detail_missing="Không thấy Git; app vẫn mở được nhưng không tự pull source.",
                status_when_missing="warning",
            ),
            _command_status(
                task_id="env:ffmpeg",
                label="FFmpeg",
                command="ffmpeg",
                detail_ok="Đã có FFmpeg cho chuyển đổi/kiểm tra audio.",
                detail_missing="Không thấy FFmpeg; một số luồng MP3/audio conversion có thể thiếu.",
                status_when_missing="warning",
            ),
            _main_python_status(),
        ]
        statuses.extend(_storage_statuses())
        statuses.append(_gpu_status())
        return statuses

    def model_setup_statuses(self, model_id: str) -> list[SetupTaskStatus]:
        spec = self.registry.get(model_id)
        model_status = self.storage.status_for(spec)
        runtime = self.runtime_status.status_for(model_id)
        statuses = [_model_payload_status(spec, model_status)]
        base = _base_runtime_status(
            spec,
            model_status,
            self.runtime_status.detector.info_for_provider(spec.provider),
        )
        if base is not None:
            statuses.append(base)
        gpu = _gpu_runtime_status(spec, runtime)
        if gpu is not None:
            statuses.append(gpu)
        return statuses

    def setup_statuses(self, model_id: str | None = None) -> list[SetupTaskStatus]:
        statuses = self.environment_statuses()
        if model_id:
            statuses.extend(self.model_setup_statuses(model_id))
        return statuses

    def install_base_for_model(self, model_id: str) -> str:
        spec = self.registry.get(model_id)
        try:
            message = install_base_runtime(spec.provider)
        except RuntimeError as exc:
            raise ConfigError(str(exc)) from exc
        self.runtime_status.detector.clear()
        return message

    def install_gpu_for_model(self, model_id: str) -> str:
        spec = self.registry.get(model_id)
        try:
            message = install_gpu_acceleration(spec.provider)
        except RuntimeError as exc:
            raise ConfigError(str(exc)) from exc
        self.runtime_status.detector.clear()
        return message


def _model_payload_status(spec: ModelSpec, model_status) -> SetupTaskStatus:
    if spec.provider in {"vieneu", "valtec"}:
        ready = model_status.hf_cached is not False
        label = "HF cache/model"
        detail_ready = "Model đã có trong HF cache dùng chung."
        detail_missing = "Chưa có đủ cache model; bấm Tải model để tải đúng repo cần cho model này."
    else:
        ready = bool(model_status.installed)
        label = "Model payload"
        detail_ready = "Payload model đã có trong storage."
        detail_missing = "Chưa tải payload model; bấm Tải model khi cần dùng."
    return SetupTaskStatus(
        task_id=f"model:{spec.model_id}:payload",
        label=label,
        scope="model",
        status="ok" if ready else "missing",
        detail=detail_ready if ready else detail_missing,
        provider=spec.provider,
        model_id=spec.model_id,
        required=spec.required,
        recommended=not ready,
        can_run=not ready,
        action_label="Tải model",
    )


def _base_runtime_status(spec: ModelSpec, model_status, runtime_info) -> SetupTaskStatus | None:
    if spec.provider == "omnivoice":
        script = base_installer_for_provider(spec.provider)
        ready = runtime_info.installed and runtime_info.torch_available
        return SetupTaskStatus(
            task_id=f"model:{spec.model_id}:base-runtime",
            label="Thư viện TTS chính",
            scope="runtime",
            status="ok" if ready else "missing",
            detail=(
                f"Python chính đã import được torch {runtime_info.torch_version}."
                if ready
                else "Môi trường chính chưa có đủ thư viện TTS/torch."
            ),
            provider=spec.provider,
            model_id=spec.model_id,
            required=True,
            recommended=not ready,
            can_run=bool(script and script.exists() and not ready),
            action_label="Cài môi trường TTS",
            script_name=script.name if script else "",
        )

    worker_name = worker_for_provider(spec.provider)
    if not worker_name:
        return None
    script = base_installer_for_provider(spec.provider)
    ready = model_status.worker_installed is True
    return SetupTaskStatus(
        task_id=f"model:{spec.model_id}:worker",
        label=f"Worker {provider_label(spec.provider)}",
        scope="worker",
        status="ok" if ready else "missing",
        detail=(
            f"Worker đã có tại {worker_install_path(worker_name)}."
            if ready
            else f"Model này cần worker riêng: {worker_name}."
        ),
        provider=spec.provider,
        model_id=spec.model_id,
        required=True,
        recommended=not ready,
        can_run=bool(script and script.exists() and not ready),
        action_label="Cài worker",
        script_name=script.name if script else "",
    )


def _gpu_runtime_status(spec: ModelSpec, runtime) -> SetupTaskStatus | None:
    script = gpu_installer_for_provider(spec.provider)
    if script is None:
        return None
    configured_cuda = configured_runtime_device(spec) == "cuda"
    ready = bool(runtime.gpu_available)
    status = "ok" if ready else ("missing" if configured_cuda else "optional")
    detail = runtime.message
    if ready:
        detail = runtime.device_name or "CUDA đã khả dụng cho provider này."
    elif not detail:
        detail = "CUDA là tùy chọn; chỉ cài nếu muốn chạy model này bằng GPU."
    return SetupTaskStatus(
        task_id=f"model:{spec.model_id}:gpu",
        label=f"CUDA cho {provider_label(spec.provider)}",
        scope="gpu",
        status=status,
        detail=detail,
        provider=spec.provider,
        model_id=spec.model_id,
        required=configured_cuda,
        recommended=configured_cuda and not ready,
        can_run=bool(script.exists() and not ready),
        action_label="Cài GPU/CUDA",
        script_name=script.name,
    )


def _main_python_status() -> SetupTaskStatus:
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / "runtime" / "python" / "python.exe",
        PROJECT_ROOT / "runtime" / "python" / "bin" / "python",
    ]
    existing = next((path for path in candidates if path.exists()), None)
    return SetupTaskStatus(
        task_id="env:python",
        label="Python môi trường chính",
        scope="environment",
        status="ok" if existing else "missing",
        detail=(
            f"Đã có Python app: {existing}"
            if existing
            else "Chưa thấy .venv/runtime Python; Start-ColinTTS.bat sẽ tạo khi sync."
        ),
    )


def _storage_statuses() -> list[SetupTaskStatus]:
    statuses: list[SetupTaskStatus] = []
    config_path = local_storage_config_path()
    config_detail = (
        f"Đang dùng cấu hình local: {config_path}"
        if config_path.exists()
        else "Chưa có storage.local.yaml; app dùng storage mặc định trong thư mục dự án."
    )
    statuses.append(
        SetupTaskStatus(
            task_id="env:storage-config",
            label="Cấu hình storage",
            scope="storage",
            status="ok" if config_path.exists() else "optional",
            detail=config_detail,
        )
    )
    for key, path in storage_roots().items():
        statuses.append(
            SetupTaskStatus(
                task_id=f"env:storage:{key}",
                label=f"Storage {key}",
                scope="storage",
                status="ok" if path.exists() else "optional",
                detail=str(path),
            )
        )
    return statuses


def _gpu_status() -> SetupTaskStatus:
    summary = host_gpu_summary()
    has_nvidia = not summary.startswith("Không thấy") and not summary.startswith("nvidia-smi không")
    return SetupTaskStatus(
        task_id="env:nvidia",
        label="NVIDIA GPU",
        scope="environment",
        status="ok" if has_nvidia else "optional",
        detail=summary,
    )


def _file_status(
    *,
    task_id: str,
    label: str,
    path: Path,
    detail_ok: str,
    detail_missing: str,
) -> SetupTaskStatus:
    return SetupTaskStatus(
        task_id=task_id,
        label=label,
        scope="environment",
        status="ok" if path.exists() else "missing",
        detail=f"{detail_ok} ({path})" if path.exists() else detail_missing,
    )


def _command_status(
    *,
    task_id: str,
    label: str,
    command: str,
    detail_ok: str,
    detail_missing: str,
    status_when_missing: str = "missing",
) -> SetupTaskStatus:
    path = shutil.which(command)
    return SetupTaskStatus(
        task_id=task_id,
        label=label,
        scope="environment",
        status="ok" if path else status_when_missing,
        detail=f"{detail_ok} ({path})" if path else detail_missing,
    )
