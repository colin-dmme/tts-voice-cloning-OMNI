"""Which model-management actions apply to the current selection.

Each action carries the exact model ids it will run on, so a GUI never has to
guess: it enables a button only when there is something to do, explains why not
otherwise, and runs the action on `state.targets` — never on the raw selection.

That matters for provider-level actions: selecting 46 Piper voices and pressing
"Cài worker" must install the Piper worker once, not 46 times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.worker_installation import (
    provider_supports_base_install,
    provider_supports_gpu_install,
)
from omni_tts_shared.schemas import ModelStatus

DOWNLOAD = "download"
IMPORT_LOCAL = "import_local"
DOWNLOAD_REQUIRED = "download_required"
REMOVE = "remove"
INSTALL_WORKER = "install_worker"
INSTALL_GPU = "install_gpu"
OPEN_STORAGE = "open"
CATALOG = "catalog"
REFRESH = "refresh"

NO_SELECTION = "Hãy chọn ít nhất một model trong bảng."


@dataclass(frozen=True)
class ActionState:
    enabled: bool
    reason: str = ""
    targets: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.enabled

    @property
    def tooltip(self) -> str:
        return self.reason


@dataclass(frozen=True)
class ModelActionPolicy:
    selection_count: int
    states: Mapping[str, ActionState] = field(default_factory=dict)

    def state(self, action: str) -> ActionState:
        return self.states.get(action, ActionState(False, NO_SELECTION))


def build_action_policy(selected: Sequence[ModelStatus]) -> ModelActionPolicy:
    """Decide button availability from the selected model statuses."""
    always_on = ActionState(True, "")
    states: dict[str, ActionState] = {
        DOWNLOAD_REQUIRED: ActionState(True, "Tải mọi model bắt buộc còn thiếu."),
        CATALOG: always_on,
        REFRESH: always_on,
    }

    if not selected:
        for action in (DOWNLOAD, IMPORT_LOCAL, REMOVE, INSTALL_WORKER, INSTALL_GPU, OPEN_STORAGE):
            states[action] = ActionState(False, NO_SELECTION)
        return ModelActionPolicy(0, states)

    states[DOWNLOAD] = _download_state(selected)
    states[IMPORT_LOCAL] = _import_local_state(selected)
    states[REMOVE] = _remove_state(selected)
    states[INSTALL_WORKER] = _provider_state(
        selected,
        provider_supports_base_install,
        "không có tác vụ cài môi trường tự động.",
    )
    states[INSTALL_GPU] = _provider_state(
        selected,
        provider_supports_gpu_install,
        "không có bộ cài GPU/CUDA (chạy CPU hoặc ONNX).",
    )
    states[OPEN_STORAGE] = _open_state(selected)
    return ModelActionPolicy(len(selected), states)


def payload_ready(item: ModelStatus) -> bool:
    """A model counts as downloaded when its payload and HF cache are both present."""
    return bool(item.installed) and item.hf_cached is not False


def _download_state(selected: Sequence[ModelStatus]) -> ActionState:
    targets = tuple(
        item.model_id
        for item in selected
        if item.storage_kind != "Remote endpoint"
        and item.source_kind != "manual"
        and not payload_ready(item)
    )
    if targets:
        return ActionState(True, f"Tải {len(targets)} model đang thiếu.", targets)
    return ActionState(False, "Các model đang chọn đã tải đủ.")


def _import_local_state(selected: Sequence[ModelStatus]) -> ActionState:
    targets = tuple(
        item.model_id
        for item in selected
        if item.source_kind == "manual" and not payload_ready(item)
    )
    if targets:
        return ActionState(
            True,
            f"Nhập {len(targets)} package local; có thể chọn thư mục bộ sưu tập hoặc thư mục package.",
            targets,
        )
    if any(item.source_kind == "manual" for item in selected):
        return ActionState(False, "Các package local đang chọn đã được nhập đủ.")
    return ActionState(False, "Model đang chọn không dùng package local.")


def _remove_state(selected: Sequence[ModelStatus]) -> ActionState:
    targets = tuple(
        item.model_id
        for item in selected
        if item.storage_kind != "Remote endpoint"
        and item.installed
        and not item.required
    )
    if targets:
        return ActionState(True, f"Gỡ {len(targets)} model đang chọn.", targets)
    if any(item.required for item in selected):
        return ActionState(False, "Model bắt buộc không gỡ được từ app.")
    return ActionState(False, "Model chưa tải nên không có gì để gỡ.")


def _provider_state(
    selected: Sequence[ModelStatus],
    supported: "callable",
    missing_suffix: str,
) -> ActionState:
    """One target per distinct worker so shared installs run exactly once.

    A provider may own multiple isolated runtimes (VieNeu v2 and VieNeu v3), so
    provider-only deduplication would silently skip one of them.
    """
    targets: list[str] = []
    unsupported: list[str] = []
    seen: set[str] = set()
    for item in selected:
        provider = item.provider
        install_key = item.worker_name or provider
        if install_key in seen:
            continue
        seen.add(install_key)
        if supported(provider):
            targets.append(item.model_id)
        else:
            unsupported.append(_provider_label(provider))
    if targets:
        detail = f"Chạy cho {len(targets)} môi trường độc lập."
        if unsupported:
            detail += " Bỏ qua: " + ", ".join(unsupported) + "."
        return ActionState(True, detail, tuple(targets))
    names = ", ".join(unsupported) or "Nhà cung cấp đang chọn"
    return ActionState(False, f"{names} {missing_suffix}")


def _open_state(selected: Sequence[ModelStatus]) -> ActionState:
    if len(selected) != 1:
        return ActionState(False, "Chỉ mở được thư mục của một model.")
    if selected[0].storage_kind == "Remote endpoint":
        return ActionState(False, "Model từ xa không có thư mục payload trên máy này.")
    return ActionState(True, "Mở thư mục lưu của model đang chọn.", (selected[0].model_id,))


def _provider_label(provider_id: str) -> str:
    descriptor = provider_descriptor(provider_id)
    return descriptor.label if descriptor else (provider_id or "Khác")
