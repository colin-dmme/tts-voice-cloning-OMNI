from __future__ import annotations

from pathlib import Path

from omni_tts_core.paths import project_path


def worker_venv_path(worker_name: str) -> Path:
    return project_path(f"engines/{worker_name}/.venv")


def worker_venv_python(worker_name: str) -> Path:
    return worker_venv_path(worker_name) / "Scripts" / "python.exe"


def worker_site_packages(worker_name: str) -> Path:
    return project_path(f"engines/{worker_name}/site-packages")


def portable_python_path() -> Path:
    return project_path("runtime/python/python.exe")


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
