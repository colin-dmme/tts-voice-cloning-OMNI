from __future__ import annotations

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.runtime_devices import (
    RuntimeDeviceDetector,
    configured_runtime_device,
)
from omni_tts_core.worker_installation import is_worker_installed
from omni_tts_shared.schemas import RuntimeStatus


class RuntimeStatusService:
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        storage: ModelStorage | None = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.storage = storage or ModelStorage(self.registry)
        self.detector = RuntimeDeviceDetector()

    def all_statuses(self) -> list[RuntimeStatus]:
        return [self.status_for(spec.model_id) for spec in self.registry.tts_models()]

    def status_for(self, model_id: str) -> RuntimeStatus:
        spec = self.registry.get(model_id)
        installed = self.storage.is_installed(spec)
        if spec.provider == "omnivoice":
            return _omnivoice_status(spec, installed, self.detector)
        if spec.provider == "vieneu":
            return _worker_status(spec, installed, "vieneu_worker", self.detector)
        if spec.provider == "qwen":
            return _worker_status(spec, installed, "qwen_worker", self.detector)
        if spec.provider == "valtec":
            return _worker_status(spec, installed, "valtec_worker", self.detector)
        if spec.provider == "f5tts":
            return _worker_status(spec, installed, "f5_worker", self.detector)
        if spec.provider == "chatterbox":
            return _worker_status(spec, installed, "chatterbox_worker", self.detector)
        return RuntimeStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            installed=installed,
            actual_device="unknown",
            message="Provider chưa có kiểm tra runtime.",
        )


def _omnivoice_status(
    spec: ModelSpec,
    installed: bool,
    detector: RuntimeDeviceDetector,
) -> RuntimeStatus:
    info = detector.info_for_provider(spec.provider)
    actual = "auto-cuda" if info.cuda_available else "auto-cpu"
    return RuntimeStatus(
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        installed=installed,
        gpu_available=info.cuda_available,
        actual_device=actual if installed else "missing",
        device_name=info.device_label if installed else "",
        message=(
            "Đã cài; Auto sẽ ưu tiên CUDA nếu môi trường chính hỗ trợ."
            if installed
            else "Chưa có model trong dự án."
        ),
    )


def _worker_status(
    spec: ModelSpec,
    installed: bool,
    worker_name: str,
    detector: RuntimeDeviceDetector,
) -> RuntimeStatus:
    if not is_worker_installed(worker_name):
        return RuntimeStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            installed=False,
            actual_device="not-installed",
            message=f"{_provider_label(spec.provider)} worker chưa cài. Chạy {_install_hint(spec.provider)}.",
        )
    info = detector.info_for_provider(spec.provider)
    configured = configured_runtime_device(spec)
    actual = configured
    runtime_warning = ""
    if configured == "auto":
        actual = "auto-cuda" if info.cuda_available else "auto-cpu"
    elif configured == "cpu" and _auto_cuda_ready(spec, info):
        actual = "auto-cuda"
    elif configured == "cuda" and not info.cuda_available:
        actual = "cuda-unavailable"
    elif configured == "cuda":
        runtime_warning = _cuda_runtime_warning(spec, info)
        if runtime_warning:
            actual = "cuda-partial"
    default_note = "Worker đã cài."
    if spec.provider == "valtec":
        default_note = "Worker đã cài; mặc định vẫn ưu tiên CPU, CUDA là tùy chọn nâng cao."
    return RuntimeStatus(
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        installed=installed,
        gpu_available=info.cuda_available,
        actual_device=actual,
        device_name=info.device_label,
        message=_runtime_message(
            default_note,
            configured,
            info.message,
            spec.provider,
            info.cuda_available,
            runtime_warning,
        ),
    )


def _runtime_message(
    default_note: str,
    configured: str,
    probe_message: str,
    provider: str,
    cuda_available: bool,
    runtime_warning: str = "",
) -> str:
    parts = [default_note, f"Cấu hình model hiện tại: {configured.upper()}."]
    if configured == "cuda" and not cuda_available:
        parts.append(f"Chưa có CUDA trong {_provider_label(provider)} worker; hãy cài worker GPU hoặc chọn model thường + Auto/CPU.")
    if runtime_warning:
        parts.append(runtime_warning)
    if probe_message:
        parts.append(probe_message)
    return " ".join(parts)


def _cuda_runtime_warning(spec: ModelSpec, info) -> str:
    if spec.provider != "vieneu":
        return ""
    mode = str(spec.runtime.get("vieneu_mode") or "").lower()
    if mode == "turbo" and not info.onnxruntime_cuda:
        return "VieNeu Turbo CUDA cần onnxruntime-gpu; hiện worker chưa có CUDAExecutionProvider."
    if mode in {"standard", "lora"} and spec.runtime.get("gguf_filename") and not info.llama_gpu_offload:
        return "VieNeu GGUF CUDA cần llama.cpp GPU offload; hiện worker chưa có backend này, nên dùng CPU hoặc VieNeu Turbo/PyTorch cho GPU."
    return ""


def _auto_cuda_ready(spec: ModelSpec, info) -> bool:
    if spec.provider != "vieneu" or not info.cuda_available:
        return False
    mode = str(spec.runtime.get("vieneu_mode") or "").lower()
    if mode == "turbo":
        return bool(info.onnxruntime_cuda)
    if mode in {"standard", "lora"} and spec.runtime.get("gguf_filename"):
        return bool(info.llama_gpu_offload)
    return True


def _provider_label(provider: str) -> str:
    return {
        "vieneu": "VieNeu",
        "qwen": "Qwen",
        "valtec": "Valtec",
        "f5tts": "F5-TTS",
        "chatterbox": "Chatterbox",
    }.get(provider, provider)


def _install_hint(provider: str) -> str:
    return {
        "vieneu": "install_vieneu_worker.bat hoặc install_vieneu_worker_cuda.bat",
        "qwen": "install_qwen_worker.bat hoặc install_qwen_worker_blackwell.bat nếu dùng RTX 50xx",
        "valtec": "install_valtec_worker.bat",
        "f5tts": "install_f5_worker.bat hoặc install_f5_worker_cuda.bat",
        "chatterbox": "install_chatterbox_worker.bat hoặc install_chatterbox_worker_cuda.bat",
    }.get(provider, "script cài tương ứng")
