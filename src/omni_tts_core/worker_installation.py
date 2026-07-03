from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from omni_tts_core.paths import PROJECT_ROOT, project_path


PROVIDER_WORKERS = {
    "vieneu": "vieneu_worker",
    "qwen": "qwen_worker",
    "valtec": "valtec_worker",
    "f5tts": "f5_worker",
    "chatterbox": "chatterbox_worker",
}

PROVIDER_LABELS = {
    "omnivoice": "OmniVoice",
    "vieneu": "VieNeu",
    "qwen": "Qwen",
    "valtec": "Valtec",
    "f5tts": "F5-TTS",
    "chatterbox": "Chatterbox",
}

_WINDOWS_BASE_INSTALLERS = {
    "omnivoice": "install_tts_deps.bat",
    "vieneu": "install_vieneu_worker.bat",
    "qwen": "install_qwen_worker.bat",
    "valtec": "install_valtec_worker.bat",
    "f5tts": "install_f5_worker.bat",
    "chatterbox": "install_chatterbox_worker.bat",
}

_LINUX_BASE_INSTALLERS = {
    "omnivoice": "scripts/install_tts_deps_linux.sh",
    "vieneu": "scripts/install_vieneu_worker_linux.sh",
    "qwen": "scripts/install_qwen_worker_linux.sh",
    "f5tts": "scripts/install_f5_worker_linux.sh",
    "chatterbox": "scripts/install_chatterbox_worker_linux.sh",
}


def worker_venv_path(worker_name: str) -> Path:
    return project_path(f"engines/{worker_name}/.venv")


def worker_venv_python(worker_name: str) -> Path:
    venv = worker_venv_path(worker_name)
    windows_python = venv / "Scripts" / "python.exe"
    if windows_python.exists():
        return windows_python
    return venv / "bin" / "python"


def worker_site_packages(worker_name: str) -> Path:
    return project_path(f"engines/{worker_name}/site-packages")


def portable_python_path() -> Path:
    windows_python = project_path("runtime/python/python.exe")
    if windows_python.exists():
        return windows_python
    return project_path("runtime/python/bin/python")


def is_worker_installed(worker_name: str) -> bool:
    if worker_venv_python(worker_name).exists():
        return True
    site_packages = worker_site_packages(worker_name)
    return (
        portable_python_path().exists()
        and site_packages.exists()
        and any(site_packages.iterdir())
    )


def worker_install_path(worker_name: str) -> Path:
    if worker_venv_python(worker_name).exists():
        return worker_venv_path(worker_name)
    site_packages = worker_site_packages(worker_name)
    if site_packages.exists():
        return site_packages
    return worker_venv_path(worker_name)


def install_worker(worker_name: str) -> None:
    """Chạy uv sync để cài môi trường Python cho worker."""
    worker_dir = project_path(f"engines/{worker_name}")
    result = subprocess.run(
        ["uv", "sync", "--inexact"],
        cwd=str(worker_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Cài {worker_name} thất bại:\n{detail}")


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider)


def worker_for_provider(provider: str) -> str | None:
    return PROVIDER_WORKERS.get(provider)


def provider_worker_installed(provider: str) -> bool | None:
    worker_name = worker_for_provider(provider)
    if not worker_name:
        return None
    return is_worker_installed(worker_name)


def base_installer_for_provider(provider: str) -> Path | None:
    script = (_WINDOWS_BASE_INSTALLERS if os.name == "nt" else _LINUX_BASE_INSTALLERS).get(provider)
    if not script:
        return None
    return PROJECT_ROOT / script


def install_base_runtime(provider: str) -> str:
    script = base_installer_for_provider(provider)
    if script is not None and script.exists():
        _run_installer_script(script, f"Cài môi trường {provider_label(provider)}")
        return f"Đã chạy xong {script.name}."
    worker_name = worker_for_provider(provider)
    if worker_name:
        install_worker(worker_name)
        return f"Đã cài worker {worker_name}."
    raise RuntimeError(f"Provider {provider} chưa có tác vụ cài môi trường tự động.")


def gpu_installer_for_provider(provider: str) -> Path | None:
    if os.name == "nt":
        blackwell = _host_gpu_is_blackwell()
        script = {
            "omnivoice": "install_tts_deps_cuda128.bat" if blackwell else "install_tts_deps_cuda126.bat",
            "vieneu": "install_vieneu_worker_cuda.bat",
            "qwen": "install_qwen_worker_blackwell.bat" if blackwell else "install_qwen_worker.bat",
            "f5tts": "install_f5_worker_cuda.bat",
            "chatterbox": "install_chatterbox_worker_cuda.bat",
        }.get(provider)
    else:
        script = {
            "omnivoice": "scripts/install_tts_deps_cuda_linux.sh",
            "vieneu": "scripts/install_vieneu_worker_cuda_linux.sh",
            "qwen": "scripts/install_qwen_worker_cuda_linux.sh",
            "f5tts": "scripts/install_f5_worker_cuda_linux.sh",
            "chatterbox": "scripts/install_chatterbox_worker_cuda_linux.sh",
        }.get(provider)
    if not script:
        return None
    return PROJECT_ROOT / script


def _host_gpu_is_blackwell() -> bool:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,compute_cap",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    text = (result.stdout or "").lower()
    return "rtx 50" in text or "5090" in text or "5080" in text or "12.0" in text


def install_gpu_acceleration(provider: str) -> str:
    script = gpu_installer_for_provider(provider)
    if script is None:
        raise RuntimeError(f"Provider {provider} chưa có script cài GPU tự động.")
    if not script.exists():
        raise RuntimeError(f"Không tìm thấy script cài GPU: {script.name}")
    _run_installer_script(script, f"Cài GPU cho {provider_label(provider)}")
    return f"Đã chạy xong {script.name}."


def host_gpu_summary() -> str:
    if not shutil.which("nvidia-smi"):
        return "Không thấy nvidia-smi; máy có thể chỉ dùng CPU hoặc driver NVIDIA chưa sẵn sàng."
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,compute_cap",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return f"Không kiểm tra được NVIDIA GPU: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return f"nvidia-smi không chạy được: {detail}"
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return "; ".join(lines) if lines else "Không thấy NVIDIA GPU trong nvidia-smi."


def _run_installer_script(script: Path, action_label: str) -> None:
    command = ["cmd", "/c", str(script)] if os.name == "nt" else ["bash", str(script)]
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{action_label} thất bại:\n{detail}")
