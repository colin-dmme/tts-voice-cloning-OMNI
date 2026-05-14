from __future__ import annotations

import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

from omni_tts_core.paths import ensure_dir
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_shared.errors import ModelDownloadError, ConfigError
from omni_tts_shared.schemas import ModelStatus


class ModelStorage:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self._size_cache: dict[Path, float] = {}

    def statuses(self) -> list[ModelStatus]:
        return [self.status_for(spec) for spec in self.registry.all()]

    def status_for(self, spec: ModelSpec) -> ModelStatus:
        size_mb = self._size_cache.get(spec.local_path)
        if size_mb is None:
            size_mb = self.size_mb(spec.local_path)
            self._size_cache[spec.local_path] = size_mb
        return ModelStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            model_type=spec.model_type,
            hf_repo=spec.hf_repo,
            local_path=spec.local_path,
            installed=self.is_installed(spec),
            required=spec.required,
            size_mb=size_mb,
            notes=spec.notes,
        )

    def is_installed(self, spec: ModelSpec) -> bool:
        return spec.local_path.exists() and any(spec.local_path.iterdir())

    def download(self, model_id: str, log_callback=None) -> ModelStatus:
        spec = self.registry.get(model_id)
        if spec.provider == "vieneu":
            raise ConfigError("VieNeu cần cài bằng install_vieneu_worker.bat, không tải bằng nút model.")
        spec.local_path.mkdir(parents=True, exist_ok=True)
        try:
            if log_callback:
                log_callback(f"Đang tải model weights: {spec.hf_repo}...")
            snapshot_download(
                repo_id=spec.hf_repo,
                local_dir=str(spec.local_path),
                cache_dir=str(ensure_dir(".hf_cache")),
                local_dir_use_symlinks=False,
            )
        except Exception as exc:
            raise ModelDownloadError(f"Tải model thất bại: {spec.hf_repo}") from exc

        # Auto-install worker dependencies for subprocess-based engines
        if spec.provider == "qwen":
            from omni_tts_core.engines.qwen_engine import QwenSubprocessEngine
            QwenSubprocessEngine.ensure_worker_ready(log_callback=log_callback)

        return self.status_for(spec)

    def remove(self, model_id: str) -> ModelStatus:
        spec = self.registry.get(model_id)
        if spec.local_path.exists():
            shutil.rmtree(spec.local_path)
        return self.status_for(spec)

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
