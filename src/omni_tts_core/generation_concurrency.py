"""Resource-aware coordination for independent text and file-queue jobs.

The UI may start both workflows at once. This coordinator decides whether the
underlying work can execute immediately or must wait for a safe resource slot.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, Event
from typing import Callable, Iterator

from omni_tts_core.progress import check_cancel
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.ui_presenters.settings_state import GenerationSettings

StatusCallback = Callable[[str], None]

_GPU_TARGETS = {"cuda", "auto-cuda", "gpu"}
_CPU_TARGETS = {"cpu", "auto-cpu"}


@dataclass(frozen=True)
class GenerationResource:
    key: str
    parallel_limit: int
    label: str


class GenerationCoordinator:
    """Limit concurrent jobs by the resource they actually compete for."""

    def __init__(self, service) -> None:
        self._service = service
        self._condition = Condition()
        self._active: dict[str, int] = {}
        self._active_outputs: set[str] = set()

    def resource_for(self, settings: GenerationSettings) -> GenerationResource:
        try:
            spec = self._service.registry.get(settings.model_id)
            provider_id = spec.provider
        except Exception:
            provider_id = "unknown"

        descriptor = provider_descriptor(provider_id)
        configured_limit = max(
            1, int(getattr(descriptor, "max_parallel_jobs", 1) or 1)
        )
        if provider_id == "higgs_remote":
            endpoint_id = str(
                getattr(settings, "remote_endpoint_id", "")
                or getattr(settings, "remote_base_url", "")
                or "default"
            )
            return GenerationResource(
                f"remote:{endpoint_id}", configured_limit, "endpoint Higgs Remote"
            )
        if self._uses_local_gpu(settings):
            # All local CUDA providers share the same physical VRAM budget.
            return GenerationResource("local-gpu", 1, "GPU cục bộ")
        return GenerationResource(
            f"cpu:{provider_id}", configured_limit, f"CPU · {provider_id}"
        )

    @contextmanager
    def acquire(
        self,
        settings: GenerationSettings,
        cancel_event: Event | None,
        status_callback: StatusCallback | None = None,
        *,
        source_path: Path | None = None,
    ) -> Iterator[GenerationResource]:
        resource = self.resource_for(settings)
        output_key = self._output_key(settings, source_path)
        waiting_reported = False
        with self._condition:
            while (
                self._active.get(resource.key, 0) >= resource.parallel_limit
                or (output_key is not None and output_key in self._active_outputs)
            ):
                check_cancel(cancel_event)
                if status_callback is not None and not waiting_reported:
                    reason = (
                        "đường dẫn đầu ra"
                        if output_key is not None and output_key in self._active_outputs
                        else resource.label
                    )
                    status_callback(
                        f"Đang chờ lượt dùng {reason}; tác vụ còn lại vẫn chạy độc lập…"
                    )
                    waiting_reported = True
                self._condition.wait(timeout=0.1)
            check_cancel(cancel_event)
            self._active[resource.key] = self._active.get(resource.key, 0) + 1
            if output_key is not None:
                self._active_outputs.add(output_key)
        try:
            yield resource
        finally:
            with self._condition:
                remaining = self._active.get(resource.key, 1) - 1
                if remaining > 0:
                    self._active[resource.key] = remaining
                else:
                    self._active.pop(resource.key, None)
                if output_key is not None:
                    self._active_outputs.discard(output_key)
                self._condition.notify_all()

    def _uses_local_gpu(self, settings: GenerationSettings) -> bool:
        target = str(getattr(settings, "runtime_target", "") or "").lower()
        if target in _CPU_TARGETS:
            return False
        if target in _GPU_TARGETS:
            return True
        try:
            status = self._service.runtime_status_for(settings.model_id)
        except Exception:
            return False
        return str(getattr(status, "actual_device", "") or "").lower() in {
            "cuda",
            "auto-cuda",
        }

    @staticmethod
    def _output_key(
        settings: GenerationSettings, source_path: Path | None
    ) -> str | None:
        raw_output_dir = getattr(settings, "output_dir", None)
        output_dir = Path(raw_output_dir) if raw_output_dir else None
        raw_stem = str(getattr(settings, "output_stem", "") or "").strip()
        if source_path is not None:
            output_dir = output_dir or source_path.parent
            stem = raw_stem or source_path.stem
        else:
            # Direct text without an explicit output directory uses a unique
            # job directory and therefore cannot collide.
            if output_dir is None:
                return None
            stem = raw_stem or "output"
        return str((output_dir / stem).expanduser().resolve(strict=False)).casefold()
