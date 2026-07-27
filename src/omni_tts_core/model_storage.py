from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from huggingface_hub import snapshot_download

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.provider_registry import provider_descriptor
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

_REPO_RUNTIME_KEYS = (
    "backbone_repo",
    "decoder_repo",
    "encoder_repo",
    "codec_repo",
    "lora_repo",
    "base_repo",
    "moss_tokenizer",
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
        cache_size_mb = (
            0.0 if _uses_ephemeral_download_cache(spec) else self._cache_size_mb(spec)
        )

        worker_installed: bool | None = None
        hf_cached: bool | None = None
        worker_path: Path | None = None
        worker_name = PROVIDER_WORKERS.get(spec.provider)
        worker_size_mb = 0.0
        if worker_name:
            worker_installed = is_worker_installed(worker_name)
            worker_path = worker_install_path(worker_name)
        if _uses_hf_cache(spec):
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
            cache_path=(
                None
                if _uses_ephemeral_download_cache(spec)
                else (hf_cache_root() if _repos_for_spec(spec) else None)
            ),
            worker_path=worker_path,
            storage_note=_storage_note_for(spec),
            worker_installed=worker_installed,
            hf_cached=hf_cached,
        )

    def is_installed(self, spec: ModelSpec) -> bool:
        if _uses_remote_endpoint(spec):
            # There is intentionally no local payload. Endpoint reachability is
            # checked from the Studio with the current, user-supplied URL.
            return True
        if _uses_hf_cache(spec):
            worker_name = PROVIDER_WORKERS.get(spec.provider)
            return bool(
                worker_name
                and is_worker_installed(worker_name)
                and self._is_hf_fully_cached(spec)
            )
        if spec.provider == "omnivoice":
            subfolder = _runtime_text(spec, "omnivoice_subfolder")
            if subfolder:
                model_path = spec.local_path / subfolder
                return model_path.exists() and any(model_path.iterdir())
        if not spec.local_path.exists():
            return False
        required_artifacts = [
            _runtime_text(spec, key)
            for key in ("model_file", "config_file")
            if _runtime_text(spec, key)
        ]
        if required_artifacts:
            return all(
                (spec.local_path / relative_path).is_file()
                for relative_path in required_artifacts
            )
        return any(spec.local_path.iterdir())

    def _status_path(self, spec: ModelSpec) -> Path:
        if _uses_hf_cache(spec):
            worker_name = PROVIDER_WORKERS.get(spec.provider)
            if worker_name:
                return worker_install_path(worker_name)
        return spec.local_path

    def download(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if _uses_remote_endpoint(spec):
            raise ConfigError(
                f"{spec.display_name} chạy trên endpoint từ xa, không tải model vào máy này."
            )
        if _uses_hf_cache(spec):
            self._ensure_worker(spec.provider)
            self._precache_hf_repos(spec)
            return self.status_for(spec)
        download_kwargs = {
            "repo_id": spec.hf_repo,
        }
        if not _uses_ephemeral_download_cache(spec):
            download_kwargs["cache_dir"] = str(ensure_hf_hub_cache_root())
        allow_patterns = _runtime_list(spec, "download_allow_patterns")
        if allow_patterns:
            download_kwargs["allow_patterns"] = allow_patterns
        try:
            self._download_folder_payload(spec, download_kwargs)
            self._verify_downloaded_model(spec)
        except Exception as exc:
            raise ModelDownloadError(f"Tải model thất bại: {spec.hf_repo}") from exc
        self._size_cache.clear()
        return self.status_for(spec)

    def remove(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if _uses_remote_endpoint(spec):
            raise ConfigError(
                f"{spec.display_name} không có payload cục bộ để gỡ."
            )
        if spec.required:
            raise ConfigError(f"{spec.display_name} là model bắt buộc, không gỡ từ app.")
        if not _uses_hf_cache(spec) and spec.local_path.exists():
            if _is_redownloadable_payload(spec):
                _safe_rmtree(spec.local_path, allowed_roots=[models_root()])
            else:
                _move_to_trash(
                    spec.local_path,
                    models_root() / ".trash",
                    allowed_roots=[models_root()],
                    label=spec.model_id,
                )
        if not _uses_ephemeral_download_cache(spec):
            for repo in _repos_for_spec(spec):
                if self._repo_used_by_other_model(repo, spec.model_id):
                    continue
                for path in hf_repo_cache_dirs(repo):
                    if path.exists():
                        _move_to_trash(
                            path,
                            hf_cache_root() / ".trash",
                            allowed_roots=[hf_cache_root()],
                            label=spec.model_id,
                        )
        self._size_cache.clear()
        return self.status_for(spec)

    def removal_preview(self, model_id: str) -> str:
        spec = self.registry.get(model_id)
        if spec.required:
            return f"{spec.display_name} là model bắt buộc nên không nên gỡ."
        paths: list[str] = []
        if not _uses_hf_cache(spec) and spec.local_path.exists():
            paths.append(f"Model payload: {spec.local_path}")
        if not _uses_ephemeral_download_cache(spec):
            for repo in _repos_for_spec(spec):
                if self._repo_used_by_other_model(repo, spec.model_id):
                    continue
                for path in hf_repo_cache_dirs(repo):
                    if path.exists():
                        paths.append(f"HF cache: {path}")
        if not paths:
            return "Không thấy payload/cache riêng để gỡ cho model này."
        joined = "\n".join(f"- {path}" for path in paths)
        if _is_redownloadable_payload(spec):
            return (
                "Sẽ xóa vĩnh viễn package model sau để giải phóng dung lượng:\n"
                f"{joined}\n\n"
                "Worker Piper dùng chung vẫn được giữ. Có thể bấm Tải model để tải lại "
                "bất kỳ lúc nào."
            )
        return (
            f"Sẽ chuyển các mục sau vào thư mục .trash (có thể phục hồi thủ công):\n"
            f"{joined}\n\nWorker dùng chung sẽ được giữ lại."
        )

    def _download_folder_payload(self, spec: ModelSpec, download_kwargs: dict) -> None:
        spec.local_path.parent.mkdir(parents=True, exist_ok=True)

        def download_into(local_dir: str) -> None:
            if _uses_ephemeral_download_cache(spec):
                with tempfile.TemporaryDirectory(
                    prefix=f".{spec.model_id}-hf-cache-",
                    dir=str(spec.local_path.parent),
                ) as cache_dir:
                    snapshot_download(
                        local_dir=local_dir,
                        cache_dir=cache_dir,
                        **download_kwargs,
                    )
                return
            snapshot_download(local_dir=local_dir, **download_kwargs)

        if spec.local_path.exists() and any(spec.local_path.iterdir()):
            download_into(str(spec.local_path))
            return
        with tempfile.TemporaryDirectory(
            prefix=f".{spec.model_id}-staging-",
            dir=str(spec.local_path.parent),
        ) as staging_dir:
            download_into(staging_dir)
            if spec.local_path.exists():
                spec.local_path.rmdir()
            shutil.move(staging_dir, spec.local_path)

    def _verify_downloaded_model(self, spec: ModelSpec) -> None:
        expected = _runtime_text(spec, "model_sha256").lower()
        if not expected:
            return
        relative_model_path = _runtime_text(spec, "model_file")
        model_path = spec.local_path / relative_model_path
        actual = _sha256_file(model_path) if model_path.is_file() else ""
        if actual == expected:
            return
        if spec.local_path.exists():
            _safe_rmtree(spec.local_path, allowed_roots=[models_root()])
        raise ModelDownloadError(
            f"Model {spec.display_name} sai SHA-256 "
            f"(mong đợi {expected}, nhận {actual or 'thiếu file'})."
        )

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
                    kwargs = {"repo_id": repo, "cache_dir": hf_cache}
                    allow_patterns = _runtime_list(spec, "download_allow_patterns")
                    if repo == spec.hf_repo and allow_patterns:
                        kwargs["allow_patterns"] = allow_patterns
                    snapshot_download(**kwargs)
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if _uses_remote_endpoint(spec):
        return "Remote endpoint"
    if _uses_hf_cache(spec):
        return "HF cache + worker"
    if spec.provider in PROVIDER_WORKERS:
        return "Model folder + worker"
    return "Model folder"


def _storage_path_for(spec: ModelSpec) -> Path | None:
    if _uses_remote_endpoint(spec):
        return None
    if _uses_hf_cache(spec):
        return hf_cache_root()
    return spec.local_path


def _storage_note_for(spec: ModelSpec) -> str:
    if _uses_remote_endpoint(spec):
        return "Model chạy trên GPU từ xa; URL và kết nối được cấu hình trong Studio."
    if spec.required:
        return "Bắt buộc cho cấu hình mặc định."
    if _uses_hf_cache(spec):
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


def _uses_hf_cache(spec: ModelSpec) -> bool:
    descriptor = provider_descriptor(spec.provider)
    return bool(descriptor and descriptor.storage_mode == "hf_cache")


def _uses_remote_endpoint(spec: ModelSpec) -> bool:
    descriptor = provider_descriptor(spec.provider)
    return bool(descriptor and descriptor.storage_mode == "remote")


def _uses_ephemeral_download_cache(spec: ModelSpec) -> bool:
    """Piper packages are self-contained and cheap to download again."""
    return spec.provider == "piper"


def _is_redownloadable_payload(spec: ModelSpec) -> bool:
    """Payloads safe to delete permanently after the user's confirmation."""
    return spec.provider == "piper" and bool(spec.hf_repo)


def _move_to_trash(
    path: Path,
    trash_root: Path,
    *,
    allowed_roots: list[Path],
    label: str,
) -> Path:
    target = path.resolve()
    allowed = [root.resolve() for root in allowed_roots]
    if not any(_is_relative_to(target, root) for root in allowed):
        roots = ", ".join(str(root) for root in allowed)
        raise ConfigError(
            f"Không gỡ vì đường dẫn nằm ngoài vùng storage cho phép: {target}. "
            f"Vùng cho phép: {roots}"
        )
    trash_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = trash_root / f"{stamp}-{label}-{target.name}"
    shutil.move(str(target), str(destination))
    return destination


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
