from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.paths import PROJECT_ROOT, project_path
from omni_tts_core.worker_installation import (
    is_worker_installed,
    portable_python_path,
    worker_site_packages,
    worker_venv_python,
)
from omni_tts_shared.errors import ConfigError


RuntimeTarget = Literal["auto", "cpu", "cuda"]
RUNTIME_TARGET_CHOICES: list[tuple[str, RuntimeTarget]] = [
    ("Auto (khuyến nghị)", "auto"),
    ("CPU", "cpu"),
    ("GPU CUDA", "cuda"),
]


@dataclass(frozen=True)
class ProviderDeviceInfo:
    provider: str
    installed: bool
    torch_available: bool = False
    cuda_available: bool = False
    torch_version: str = ""
    device_name: str = ""
    capability: str = ""
    arch_list: tuple[str, ...] = ()
    total_vram_mb: int = 0
    onnxruntime_cuda: bool = False
    llama_gpu_offload: bool = False
    message: str = ""

    @property
    def device_label(self) -> str:
        if self.cuda_available:
            suffix = f", {self.total_vram_mb} MB VRAM" if self.total_vram_mb else ""
            return f"CUDA - {self.device_name}{suffix}".strip()
        if self.torch_available:
            return "CPU"
        return "unknown"


class RuntimeDeviceDetector:
    def __init__(self) -> None:
        self._cache: dict[str, ProviderDeviceInfo] = {}

    def info_for_provider(self, provider: str) -> ProviderDeviceInfo:
        if provider not in self._cache:
            self._cache[provider] = self._detect(provider)
        return self._cache[provider]

    def clear(self) -> None:
        self._cache.clear()

    def _detect(self, provider: str) -> ProviderDeviceInfo:
        if provider == "omnivoice":
            return _probe_current_python(provider)
        if provider == "vieneu":
            return _probe_worker(provider, "vieneu_worker")
        if provider == "qwen":
            return _probe_worker(provider, "qwen_worker")
        if provider == "valtec":
            return _probe_worker(provider, "valtec_worker")
        if provider == "f5tts":
            return _probe_worker(provider, "f5_worker")
        if provider == "chatterbox":
            return _probe_worker(provider, "chatterbox_worker")
        return ProviderDeviceInfo(provider=provider, installed=False, message="Provider chưa có detector.")


class RuntimeDevicePolicy:
    def __init__(self, detector: RuntimeDeviceDetector | None = None) -> None:
        self.detector = detector or RuntimeDeviceDetector()

    def payload_for(self, spec: ModelSpec, target: str | None, *, mode: str | None = None) -> dict:
        target = normalize_runtime_target(target)
        if target == "auto":
            return self._auto_payload_for(spec, mode=mode)
        self._ensure_supported(spec, target, mode=mode)
        if spec.provider == "qwen":
            return {"device_map": "cuda:0" if target == "cuda" else "cpu"}
        if spec.provider == "f5tts":
            return {"device": "cuda" if target == "cuda" else "cpu"}
        if spec.provider == "chatterbox":
            return {"device": "cuda" if target == "cuda" else "cpu"}
        if spec.provider == "valtec":
            return {"device": target}
        if spec.provider == "vieneu":
            return _vieneu_device_payload(mode or str(spec.runtime.get("vieneu_mode") or ""), target)
        return {}

    def _auto_payload_for(self, spec: ModelSpec, *, mode: str | None = None) -> dict:
        configured = configured_runtime_device(spec)
        if configured == "cuda":
            self._ensure_supported(spec, "cuda", mode=mode)
            return {}
        if spec.provider != "vieneu":
            return {}
        if not self._vieneu_auto_cuda_ready(spec, mode=mode):
            return {}
        return _vieneu_device_payload(mode or str(spec.runtime.get("vieneu_mode") or ""), "cuda")

    def _vieneu_auto_cuda_ready(self, spec: ModelSpec, *, mode: str | None = None) -> bool:
        info = self.detector.info_for_provider(spec.provider)
        if not info.cuda_available:
            return False
        active_mode = (mode or str(spec.runtime.get("vieneu_mode") or "")).lower()
        if active_mode == "turbo":
            return info.onnxruntime_cuda
        if active_mode in {"standard", "lora"} and spec.runtime.get("gguf_filename"):
            return info.llama_gpu_offload
        return True

    def _ensure_supported(
        self,
        spec: ModelSpec,
        target: RuntimeTarget,
        *,
        mode: str | None = None,
    ) -> None:
        if target != "cuda":
            return
        info = self.detector.info_for_provider(spec.provider)
        if not info.cuda_available:
            install_hint = {
                "omnivoice": "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model OmniVoice.",
                "vieneu": "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model VieNeu.",
                "qwen": "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model Qwen.",
                "valtec": "Valtec worker hiện mặc định CPU; cần cài worker có PyTorch CUDA trước.",
                "f5tts": "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model F5-TTS.",
                "chatterbox": "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model Chatterbox.",
            }.get(spec.provider, "Hãy kiểm tra CUDA runtime.")
            raise ConfigError(f"CUDA chưa khả dụng cho {spec.provider}. {install_hint}")
        if spec.provider == "vieneu":
            active_mode = (mode or str(spec.runtime.get("vieneu_mode") or "")).lower()
            if active_mode == "turbo" and not info.onnxruntime_cuda:
                raise ConfigError(
                    "VieNeu Turbo CUDA cần onnxruntime-gpu trong worker. "
                    "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model VieNeu."
                )
            if active_mode in {"standard", "lora"} and spec.runtime.get("gguf_filename") and not info.llama_gpu_offload:
                raise ConfigError(
                    "VieNeu GGUF CUDA cần llama.cpp có GPU offload trong worker. "
                    "Worker hiện chưa có backend này; hãy dùng CPU/Auto hoặc dùng VieNeu Turbo/PyTorch cho GPU."
                )


def normalize_runtime_target(value: str | None) -> RuntimeTarget:
    value = (value or "auto").strip().lower()
    if value in {"auto", "cpu", "cuda"}:
        return value  # type: ignore[return-value]
    return "auto"


def runtime_target_label(value: str | None) -> str:
    target = normalize_runtime_target(value)
    return {
        "auto": "Auto",
        "cpu": "CPU",
        "cuda": "GPU CUDA",
    }[target]


def configured_runtime_device(spec: ModelSpec) -> str:
    values = {
        str(value).strip().lower()
        for key, value in spec.runtime.items()
        if key in {"device", "backbone_device", "codec_device", "pytorch_device"} and value
    }
    if "cuda" in values:
        return "cuda"
    if "cpu" in values:
        return "cpu"
    return "auto"


def _vieneu_device_payload(mode: str, target: RuntimeTarget) -> dict:
    mode = (mode or "").strip().lower()
    if mode == "turbo":
        return {"device": target}
    return {
        "backbone_device": target,
        "codec_device": target,
        "pytorch_device": target,
    }


def _probe_current_python(provider: str) -> ProviderDeviceInfo:
    try:
        import torch
    except Exception as exc:
        return ProviderDeviceInfo(
            provider=provider,
            installed=False,
            message=f"Không import được torch: {exc}",
        )
    return _torch_module_info(provider, torch)


def _probe_worker(provider: str, worker_name: str) -> ProviderDeviceInfo:
    if not is_worker_installed(worker_name):
        return ProviderDeviceInfo(provider=provider, installed=False, message="Worker chưa cài.")
    python_path, python_paths = _worker_runtime(worker_name)
    env = dict(os.environ)
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    try:
        completed = subprocess.run(
            [str(python_path), "-c", _TORCH_PROBE_CODE],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception as exc:
        return ProviderDeviceInfo(
            provider=provider,
            installed=True,
            message=f"Không kiểm tra được worker: {exc}",
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return ProviderDeviceInfo(
            provider=provider,
            installed=True,
            message=f"Worker không chạy được probe: {detail}",
        )
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return ProviderDeviceInfo(
            provider=provider,
            installed=True,
            message=f"Probe không trả JSON hợp lệ: {exc}",
        )
    return ProviderDeviceInfo(
        provider=provider,
        installed=True,
        torch_available=bool(data.get("torch_available")),
        cuda_available=bool(data.get("cuda_available")) and not _unsupported_arch_message(
            str(data.get("capability") or ""),
            data.get("arch_list") or [],
        ),
        torch_version=str(data.get("torch_version") or ""),
        device_name=str(data.get("device_name") or ""),
        capability=str(data.get("capability") or ""),
        arch_list=tuple(str(item) for item in (data.get("arch_list") or [])),
        total_vram_mb=int(data.get("total_vram_mb") or 0),
        onnxruntime_cuda=bool(data.get("onnxruntime_cuda")),
        llama_gpu_offload=bool(data.get("llama_gpu_offload")),
        message=str(data.get("message") or "") or _unsupported_arch_message(
            str(data.get("capability") or ""),
            data.get("arch_list") or [],
        ),
    )


def _worker_runtime(worker_name: str) -> tuple[Path, list[Path]]:
    portable_python = portable_python_path()
    portable_site = worker_site_packages(worker_name)
    worker_dir = project_path(f"engines/{worker_name}")
    if portable_python.exists() and portable_site.exists():
        paths = [worker_dir, portable_site]
        vendor = worker_dir / "vendor" / "valtec-tts"
        if vendor.exists():
            paths.append(vendor)
        return portable_python, paths
    return worker_venv_python(worker_name), []


def _torch_module_info(provider: str, torch_module) -> ProviderDeviceInfo:
    cuda_available = bool(torch_module.cuda.is_available())
    device_name = ""
    capability = ""
    total_vram_mb = 0
    arch_list: list[str] = []
    if cuda_available:
        try:
            device_name = str(torch_module.cuda.get_device_name(0))
            major, minor = torch_module.cuda.get_device_capability(0)
            capability = f"{major}.{minor}"
            props = torch_module.cuda.get_device_properties(0)
            total_vram_mb = int(props.total_memory / 1024 / 1024)
            arch_list = [str(item) for item in torch_module.cuda.get_arch_list()]
        except Exception:
            pass
    arch_warning = _unsupported_arch_message(capability, arch_list)
    return ProviderDeviceInfo(
        provider=provider,
        installed=True,
        torch_available=True,
        cuda_available=cuda_available and not arch_warning,
        torch_version=str(getattr(torch_module, "__version__", "")),
        device_name=device_name,
        capability=capability,
        arch_list=tuple(arch_list),
        total_vram_mb=total_vram_mb,
        message=arch_warning,
    )


def _unsupported_arch_message(capability: str, arch_list) -> str:
    if not capability or not arch_list:
        return ""
    arch = "sm_" + capability.replace(".", "")
    arch_values = {str(item) for item in arch_list}
    if arch in arch_values:
        return ""
    if arch == "sm_120":
        return (
            "GPU RTX 50xx/Blackwell cần PyTorch CUDA 12.8+ có sm_120. "
            "Mở tab Quản lý model và bấm Cài GPU/CUDA cho model đang dùng."
        )
    return f"PyTorch hiện tại không có kernel cho compute capability {arch}."


_TORCH_PROBE_CODE = r"""
import json
data = {
    "torch_available": False,
    "cuda_available": False,
    "torch_version": "",
    "device_name": "",
    "capability": "",
    "arch_list": [],
    "total_vram_mb": 0,
    "onnxruntime_cuda": False,
    "llama_gpu_offload": False,
    "message": "",
}
try:
    import torch
    data["torch_available"] = True
    data["torch_version"] = str(getattr(torch, "__version__", ""))
    data["cuda_available"] = bool(torch.cuda.is_available())
    if data["cuda_available"]:
        data["device_name"] = str(torch.cuda.get_device_name(0))
        major, minor = torch.cuda.get_device_capability(0)
        data["capability"] = f"{major}.{minor}"
        data["total_vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024)
        data["arch_list"] = [str(item) for item in torch.cuda.get_arch_list()]
except Exception as exc:
    data["message"] = str(exc)
try:
    import onnxruntime as ort
    data["onnxruntime_cuda"] = "CUDAExecutionProvider" in ort.get_available_providers()
except Exception:
    pass
try:
    import llama_cpp
    support = getattr(llama_cpp, "llama_supports_gpu_offload", None)
    data["llama_gpu_offload"] = bool(support()) if callable(support) else False
except Exception:
    pass
print(json.dumps(data, ensure_ascii=False))
"""
