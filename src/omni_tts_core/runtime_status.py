from __future__ import annotations

from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.paths import project_path
from omni_tts_shared.schemas import RuntimeStatus


class RuntimeStatusService:
    def __init__(
        self,
        registry: ModelRegistry | None = None,
        storage: ModelStorage | None = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.storage = storage or ModelStorage(self.registry)

    def all_statuses(self) -> list[RuntimeStatus]:
        return [self.status_for(spec.model_id) for spec in self.registry.tts_models()]

    def status_for(self, model_id: str) -> RuntimeStatus:
        spec = self.registry.get(model_id)
        installed = self.storage.is_installed(spec)
        if spec.provider == "omnivoice":
            return _omnivoice_status(spec, installed)
        if spec.provider == "vieneu":
            return _vieneu_status(spec, installed)
        if spec.provider == "qwen":
            return _qwen_status(spec, installed)
        return RuntimeStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            installed=installed,
            actual_device="unknown",
            message="Provider chưa có kiểm tra runtime.",
        )


def _omnivoice_status(spec: ModelSpec, installed: bool) -> RuntimeStatus:
    return RuntimeStatus(
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        installed=installed,
        actual_device="auto" if installed else "missing",
        message=(
            "Đã cài; thiết bị sẽ tự chọn khi tạo audio."
            if installed
            else "Chưa có model trong dự án."
        ),
    )


def _vieneu_status(spec: ModelSpec, installed: bool) -> RuntimeStatus:
    python_path = project_path("engines/vieneu_worker/.venv/Scripts/python.exe")
    if not python_path.exists():
        return RuntimeStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            installed=False,
            actual_device="not-installed",
            message="VieNeu worker chưa cài. Chạy install_vieneu_worker.bat.",
        )
    return RuntimeStatus(
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        installed=installed,
        actual_device="worker",
        device_name="VieNeu worker",
        message="Worker đã cài; runtime chi tiết sẽ kiểm tra khi tạo audio.",
    )


def _qwen_status(spec: ModelSpec, installed: bool) -> RuntimeStatus:
    python_path = project_path("engines/qwen_worker/.venv/Scripts/python.exe")
    if not python_path.exists():
        return RuntimeStatus(
            model_id=spec.model_id,
            display_name=spec.display_name,
            provider=spec.provider,
            installed=False,
            actual_device="not-installed",
            message="Qwen worker chưa cài. Chạy install_qwen_worker.bat.",
        )
    return RuntimeStatus(
        model_id=spec.model_id,
        display_name=spec.display_name,
        provider=spec.provider,
        installed=installed,
        actual_device="worker",
        device_name="Qwen worker",
        message="Worker đã cài; GPU/CPU sẽ kiểm tra khi tạo audio.",
    )
