from __future__ import annotations

import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.storage_paths import (
    ensure_hf_hub_cache_root,
    hf_cache_root,
    hf_repo_cache_dirs,
    models_root,
)
from omni_tts_core.worker_installation import (
    PROVIDER_WORKERS,
    install_base_runtime,
    is_worker_installed,
    worker_install_path,
)
from omni_tts_shared.errors import ModelDownloadError, ConfigError
from omni_tts_shared.schemas import ModelStatus

_HF_CACHE_PROVIDERS = ("vieneu", "valtec")
_REPO_RUNTIME_KEYS = (
    "backbone_repo",
    "decoder_repo",
    "encoder_repo",
    "codec_repo",
    "lora_repo",
    "base_repo",
)


class ModelStorage:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self._size_cache: dict[tuple[Path, bool], float] = {}

    def statuses(self) -> list[ModelStatus]:
        return [self.status_for(spec) for spec in self.registry.all()]

    def status_for(self, spec: ModelSpec) -> ModelStatus:
        local_path = self._status_path(spec)
        size_mb = self._cached_size(spec.local_path)
        cache_size_mb = self._cache_size_mb(spec)

        worker_installed: bool | None = None
        hf_cached: bool | None = None
        worker_path: Path | None = None
        worker_name = PROVIDER_WORKERS.get(spec.provider)
        worker_size_mb = 0.0
        if worker_name:
            worker_installed = is_worker_installed(worker_name)
            worker_path = worker_install_path(worker_name)
        if spec.provider in _HF_CACHE_PROVIDERS:
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
            cache_size_mb=cache_size_mb,
            worker_size_mb=worker_size_mb,
            total_size_mb=round(size_mb + cache_size_mb, 2),
            notes=spec.notes,
            usage=_usage_for(spec),
            category=str(spec.catalog_info.get("category") or ""),
            storage_kind=_storage_kind(spec),
            storage_path=_storage_path_for(spec),
            cache_path=hf_cache_root() if _repos_for_spec(spec) else None,
            worker_path=worker_path,
            storage_note=_storage_note_for(spec),
            worker_installed=worker_installed,
            hf_cached=hf_cached,
        )

    def is_installed(self, spec: ModelSpec) -> bool:
        if spec.provider in _HF_CACHE_PROVIDERS:
            worker_name = PROVIDER_WORKERS.get(spec.provider)
            return bool(worker_name and is_worker_installed(worker_name))
        if spec.provider == "omnivoice":
            subfolder = _runtime_text(spec, "omnivoice_subfolder")
            if subfolder:
                model_path = spec.local_path / subfolder
                return model_path.exists() and any(model_path.iterdir())
        return spec.local_path.exists() and any(spec.local_path.iterdir())

    def _status_path(self, spec: ModelSpec) -> Path:
        if spec.provider in _HF_CACHE_PROVIDERS:
            worker_name = PROVIDER_WORKERS.get(spec.provider)
            if worker_name:
                return worker_install_path(worker_name)
        return spec.local_path

    def download(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if spec.provider in _HF_CACHE_PROVIDERS:
            self._ensure_worker(spec.provider)
            self._precache_hf_repos(spec)
            return self.status_for(spec)
        spec.local_path.mkdir(parents=True, exist_ok=True)
        download_kwargs = {
            "repo_id": spec.hf_repo,
            "local_dir": str(spec.local_path),
            "cache_dir": str(ensure_hf_hub_cache_root()),
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
        if spec.required:
            raise ConfigError(f"{spec.display_name} là model bắt buộc, không gỡ từ app.")
        if spec.provider not in _HF_CACHE_PROVIDERS and spec.local_path.exists():
            _safe_rmtree(spec.local_path, allowed_roots=[models_root()])
        for repo in _repos_for_spec(spec):
            if self._repo_used_by_other_model(repo, spec.model_id):
                continue
            for path in hf_repo_cache_dirs(repo):
                if path.exists():
                    _safe_rmtree(path, allowed_roots=[hf_cache_root()])
        self._size_cache.clear()
        return self.status_for(spec)

    def removal_preview(self, model_id: str) -> str:
        spec = self.registry.get(model_id)
        if spec.required:
            return f"{spec.display_name} là model bắt buộc nên không nên gỡ."
        paths: list[str] = []
        if spec.provider not in _HF_CACHE_PROVIDERS and spec.local_path.exists():
            paths.append(f"Model payload: {spec.local_path}")
        for repo in _repos_for_spec(spec):
            if self._repo_used_by_other_model(repo, spec.model_id):
                continue
            for path in hf_repo_cache_dirs(repo):
                if path.exists():
                    paths.append(f"HF cache: {path}")
        if not paths:
            return "Không thấy payload/cache riêng để gỡ cho model này."
        joined = "\n".join(f"- {path}" for path in paths)
        return f"Sẽ gỡ các mục sau:\n{joined}"

    # ------------------------------------------------------------------
    # Worker & HF cache helpers
    # ------------------------------------------------------------------

    def _ensure_worker(self, provider: str) -> None:
        worker_name = PROVIDER_WORKERS.get(provider)
        if not worker_name:
            raise ConfigError(f"Provider {provider} chưa có worker được khai báo.")
        if not is_worker_installed(worker_name):
            try:
                install_base_runtime(provider)
            except RuntimeError as exc:
                raise ConfigError(str(exc)) from exc

    def _precache_hf_repos(self, spec: ModelSpec) -> None:
        hf_cache = str(ensure_hf_hub_cache_root())
        for repo in _repos_for_spec(spec):
            if not self.is_hf_cached(repo):
                try:
                    snapshot_download(repo_id=repo, cache_dir=hf_cache)
                except Exception as exc:
                    raise ModelDownloadError(f"Tải model thất bại: {repo}") from exc

    def _is_hf_fully_cached(self, spec: ModelSpec) -> bool:
        return all(self.is_hf_cached(repo) for repo in _repos_for_spec(spec))

    @staticmethod
    def is_hf_cached(hf_repo: str) -> bool:
        for cache_dir in hf_repo_cache_dirs(hf_repo):
            snapshots = cache_dir / "snapshots"
            if snapshots.exists() and any(snapshots.iterdir()):
                return True
        return False

    @staticmethod
    def size_mb(path: Path, include_venv: bool = False) -> float:
        if not path.exists():
            return 0.0
        if path.name == ".venv" and not include_venv:
            return 0.0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return round(total / (1024 * 1024), 2)

    def _cached_size(self, path: Path, include_venv: bool = False) -> float:
        key = (path, include_venv)
        size_mb = self._size_cache.get(key)
        if size_mb is None:
            size_mb = self.size_mb(path, include_venv=include_venv)
            self._size_cache[key] = size_mb
        return size_mb

    def _cache_size_mb(self, spec: ModelSpec) -> float:
        total = 0.0
        seen: set[Path] = set()
        for repo in _repos_for_spec(spec):
            for path in hf_repo_cache_dirs(repo):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                total += self._cached_size(path)
        return round(total, 2)

    def _repo_used_by_other_model(self, repo: str, model_id: str) -> bool:
        for other in self.registry.all():
            if other.model_id == model_id:
                continue
            if repo in _repos_for_spec(other):
                return True
        return False


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


def _repos_for_spec(spec: ModelSpec) -> list[str]:
    repos: list[str] = []
    if spec.hf_repo:
        repos.append(spec.hf_repo)
    for key in _REPO_RUNTIME_KEYS:
        value = spec.runtime.get(key)
        if value:
            repos.append(str(value))
    deduped: list[str] = []
    for repo in repos:
        if repo not in deduped:
            deduped.append(repo)
    return deduped


def _usage_for(spec: ModelSpec) -> str:
    info = spec.catalog_info
    for key in ("recommend_for", "description", "highlight"):
        value = str(info.get(key) or "").strip()
        if value:
            return value
    return spec.notes


def _storage_kind(spec: ModelSpec) -> str:
    if spec.provider in _HF_CACHE_PROVIDERS:
        return "HF cache + worker"
    if spec.provider in PROVIDER_WORKERS:
        return "Model folder + worker"
    return "Model folder"


def _storage_path_for(spec: ModelSpec) -> Path:
    if spec.provider in _HF_CACHE_PROVIDERS:
        return hf_cache_root()
    return spec.local_path


def _storage_note_for(spec: ModelSpec) -> str:
    if spec.required:
        return "Bắt buộc cho cấu hình mặc định."
    if spec.provider in _HF_CACHE_PROVIDERS:
        return "Model nằm trong HF cache; worker cài riêng."
    if spec.provider in PROVIDER_WORKERS:
        return "Cần cả model payload và worker riêng."
    return "Tải khi cần dùng."


def _safe_rmtree(path: Path, allowed_roots: list[Path]) -> None:
    target = path.resolve()
    allowed = [root.resolve() for root in allowed_roots]
    if not any(_is_relative_to(target, root) for root in allowed):
        roots = ", ".join(str(root) for root in allowed)
        raise ConfigError(f"Không gỡ vì đường dẫn nằm ngoài vùng storage cho phép: {target}. Vùng cho phép: {roots}")
    shutil.rmtree(target)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
