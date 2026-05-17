from __future__ import annotations

import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

from omni_tts_core.paths import ensure_dir, project_path
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.worker_installation import (
    install_worker,
    is_worker_installed,
    worker_install_path,
)
from omni_tts_shared.errors import ModelDownloadError, ConfigError
from omni_tts_shared.schemas import ModelStatus

_WORKER_PROVIDERS = ("vieneu", "valtec")


class ModelStorage:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self._size_cache: dict[Path, float] = {}

    def statuses(self) -> list[ModelStatus]:
        return [self.status_for(spec) for spec in self.registry.all()]

    def status_for(self, spec: ModelSpec) -> ModelStatus:
        local_path = self._status_path(spec)
        size_path = spec.local_path
        size_mb = self._size_cache.get(size_path)
        if size_mb is None:
            size_mb = self.size_mb(size_path)
            self._size_cache[size_path] = size_mb

        worker_installed: bool | None = None
        hf_cached: bool | None = None
        if spec.provider in _WORKER_PROVIDERS:
            worker_installed = is_worker_installed(f"{spec.provider}_worker")
            hf_cached = self._is_hf_fully_cached(spec)

        return ModelStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            model_type=spec.model_type,
            hf_repo=spec.hf_repo,
            local_path=local_path,
            installed=self.is_installed(spec),
            required=spec.required,
            size_mb=size_mb,
            notes=spec.notes,
            worker_installed=worker_installed,
            hf_cached=hf_cached,
        )

    def is_installed(self, spec: ModelSpec) -> bool:
        if spec.provider in _WORKER_PROVIDERS:
            return is_worker_installed(f"{spec.provider}_worker")
        if spec.provider == "omnivoice":
            subfolder = _runtime_text(spec, "omnivoice_subfolder")
            if subfolder:
                model_path = spec.local_path / subfolder
                return model_path.exists() and any(model_path.iterdir())
        return spec.local_path.exists() and any(spec.local_path.iterdir())

    def _status_path(self, spec: ModelSpec) -> Path:
        if spec.provider in _WORKER_PROVIDERS:
            return worker_install_path(f"{spec.provider}_worker")
        return spec.local_path

    def download(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if spec.provider in _WORKER_PROVIDERS:
            self._ensure_worker(spec.provider)
            self._precache_hf_repos(spec)
            return self.status_for(spec)
        spec.local_path.mkdir(parents=True, exist_ok=True)
        download_kwargs = {
            "repo_id": spec.hf_repo,
            "local_dir": str(spec.local_path),
            "cache_dir": str(ensure_dir(".hf_cache")),
            "local_dir_use_symlinks": False,
        }
        allow_patterns = _runtime_list(spec, "download_allow_patterns")
        if allow_patterns:
            download_kwargs["allow_patterns"] = allow_patterns
        try:
            snapshot_download(**download_kwargs)
        except Exception as exc:
            raise ModelDownloadError(f"Tải model thất bại: {spec.hf_repo}") from exc
        return self.status_for(spec)

    def remove(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if spec.local_path.exists():
            shutil.rmtree(spec.local_path)
        return self.status_for(spec)

    # ------------------------------------------------------------------
    # Worker & HF cache helpers
    # ------------------------------------------------------------------

    def _ensure_worker(self, provider: str) -> None:
        if not is_worker_installed(f"{provider}_worker"):
            try:
                install_worker(f"{provider}_worker")
            except RuntimeError as exc:
                raise ConfigError(str(exc)) from exc

    def _precache_hf_repos(self, spec: ModelSpec) -> None:
        repos = [spec.hf_repo]
        backbone = spec.runtime.get("backbone_repo")
        if backbone and backbone != spec.hf_repo:
            repos.append(backbone)
        hf_cache = str(ensure_dir(".hf_cache"))
        for repo in repos:
            if not self.is_hf_cached(repo):
                try:
                    snapshot_download(repo_id=repo, cache_dir=hf_cache)
                except Exception as exc:
                    raise ModelDownloadError(f"Tải model thất bại: {repo}") from exc

    def _is_hf_fully_cached(self, spec: ModelSpec) -> bool:
        if not self.is_hf_cached(spec.hf_repo):
            return False
        backbone = spec.runtime.get("backbone_repo")
        if backbone and backbone != spec.hf_repo and not self.is_hf_cached(backbone):
            return False
        return True

    @staticmethod
    def is_hf_cached(hf_repo: str) -> bool:
        folder = "models--" + hf_repo.replace("/", "--")
        snapshots = project_path(f".hf_cache/hub/{folder}/snapshots")
        return snapshots.exists() and any(snapshots.iterdir())

    @staticmethod
    def size_mb(path: Path) -> float:
        if not path.exists():
            return 0.0
        if path.name == ".venv":
            return 0.0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return round(total / (1024 * 1024), 2)


def _runtime_text(spec: ModelSpec, key: str) -> str:
    value = spec.runtime.get(key)
    return str(value).strip() if value else ""


def _runtime_list(spec: ModelSpec, key: str) -> list[str]:
    value = spec.runtime.get(key)
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return []
