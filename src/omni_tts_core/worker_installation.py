from __future__ import annotations

import os
import subprocess
from pathlib import Path

from omni_tts_core.paths import PROJECT_ROOT, project_path


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


def gpu_installer_for_provider(provider: str) -> Path | None:
    if os.name == "nt":
        script = {
            "omnivoice": "install_tts_deps_cuda126.bat",
            "vieneu": "install_vieneu_worker_cuda.bat",
            "qwen": "install_qwen_worker.bat",
        }.get(provider)
    else:
        script = {
            "omnivoice": "scripts/install_tts_deps_cuda_linux.sh",
            "vieneu": "scripts/install_vieneu_worker_cuda_linux.sh",
            "qwen": "scripts/install_qwen_worker_cuda_linux.sh",
        }.get(provider)
    if not script:
        return None
    return PROJECT_ROOT / script


def install_gpu_acceleration(provider: str) -> str:
    script = gpu_installer_for_provider(provider)
    if script is None:
        raise RuntimeError(f"Provider {provider} chưa có script cài GPU tự động.")
    if not script.exists():
        raise RuntimeError(f"Không tìm thấy script cài GPU: {script.name}")
    command = ["cmd", "/c", str(script)] if os.name == "nt" else ["bash", str(script)]
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Cài GPU cho {provider} thất bại:\n{detail}")
    return f"Đã chạy xong {script.name}."
