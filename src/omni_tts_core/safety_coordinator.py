"""Global GPU safety coordinator.

Provides two things the UI and the AppController need:

1. ``SafetyGate.wait_before_generation`` — a preflight gate that blocks before
   generation whenever the effective device is CUDA, for *every* provider (not
   only Chatterbox). It reuses the existing ``GpuSafetyGuard.wait_until_safe``
   semantics and JSONL logging.
2. ``SafetyGate.assess`` — a lightweight display-state evaluation used to colour
   the hardware chip and drive the temperature-chart warning line.

Non-goal (tracked follow-up): mid-generation suspend/resume for non-Chatterbox
workers. That needs each engine to pass ``supervisor_callback`` into
``run_worker_process``; Chatterbox already does its own runtime cooldown.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable

from omni_tts_core.gpu_safety import GpuSafetyConfig, GpuSafetyGuard
from omni_tts_core.hardware_monitor import HardwareProbe, HardwareSnapshot, to_gpu_snapshot
from omni_tts_core.service import TtsService
from omni_tts_core.ui_presenters.settings_state import GenerationSettings

StatusCallback = Callable[[str], None]

# Effective devices that mean "CUDA is in play" for gating purposes.
_CUDA_DEVICES = {"cuda", "auto-cuda"}
# Explicit runtime targets that force CPU regardless of model capability.
_CPU_TARGETS = {"cpu", "auto-cpu"}
_CUDA_TARGETS = {"cuda", "auto-cuda", "gpu"}

DEFAULT_WARNING_TEMPERATURE_C = 75
DEFAULT_ABORT_TEMPERATURE_C = 82


@dataclass(frozen=True)
class SafetyAssessment:
    level: str  # "ok" | "warning" | "hot" | "unavailable"
    reasons: list[str]
    snapshot: HardwareSnapshot
    warning_temperature_c: int
    abort_temperature_c: int


class SafetyGate:
    def __init__(self, service: TtsService, probe: HardwareProbe | None = None) -> None:
        self._service = service
        self._probe = probe or HardwareProbe()

    @property
    def probe(self) -> HardwareProbe:
        return self._probe

    def applies_to(self, settings: GenerationSettings) -> bool:
        """True when GPU safety preflight should gate this generation."""
        if not settings.gpu_safety_enabled:
            return False
        target = str(settings.runtime_target or "").lower()
        if target in _CPU_TARGETS:
            return False
        if target in _CUDA_TARGETS:
            return True
        # "auto"/unknown target: consult the resolved device for the model.
        try:
            status = self._service.runtime_status_for(settings.model_id)
        except Exception:
            return False
        return status.actual_device in _CUDA_DEVICES

    def guard_for(self, settings: GenerationSettings) -> GpuSafetyGuard:
        spec = self._service.registry.get(settings.model_id)
        config = GpuSafetyConfig.from_runtime(spec.runtime, _overrides(settings))
        return GpuSafetyGuard(
            config,
            snapshot_reader=lambda: to_gpu_snapshot(self._probe.snapshot()),
        )

    def wait_before_generation(
        self,
        settings: GenerationSettings,
        cancel_event: Event | None,
        status_callback: StatusCallback | None,
    ) -> None:
        if not self.applies_to(settings):
            return
        # Chatterbox performs its own preflight + runtime cooldown inside the
        # engine; skip the outer gate to avoid double-waiting.
        if self._service.registry.get(settings.model_id).provider == "chatterbox":
            return
        guard = self.guard_for(settings)
        guard.wait_until_safe(cancel_event, status_callback)

    def assess(
        self,
        snapshot: HardwareSnapshot,
        settings: GenerationSettings | None = None,
    ) -> SafetyAssessment:
        warning = _threshold(settings, "gpu_start_temperature_c", DEFAULT_WARNING_TEMPERATURE_C)
        abort = _threshold(settings, "gpu_abort_temperature_c", DEFAULT_ABORT_TEMPERATURE_C)
        if not snapshot.has_gpu:
            return SafetyAssessment("unavailable", [], snapshot, warning, abort)
        temperature = snapshot.gpu_temperature_c or 0.0
        reasons: list[str] = []
        if temperature >= abort:
            reasons.append(f"GPU {temperature:.0f}°C ≥ ngưỡng dừng {abort}°C")
            level = "hot"
        elif temperature >= warning:
            reasons.append(f"GPU {temperature:.0f}°C ≥ ngưỡng cảnh báo {warning}°C")
            level = "warning"
        else:
            level = "ok"
        free = snapshot.gpu_memory_free_mb
        if settings is not None and free is not None:
            minimum = settings.gpu_minimum_free_vram_mb or 0
            if minimum and free < minimum:
                reasons.append(f"VRAM trống {free} MB < {minimum} MB")
                if level == "ok":
                    level = "warning"
        return SafetyAssessment(level, reasons, snapshot, warning, abort)


def _overrides(settings: GenerationSettings) -> dict:
    return {
        "gpu_safety_enabled": settings.gpu_safety_enabled,
        "gpu_start_temperature_c": settings.gpu_start_temperature_c,
        "gpu_abort_temperature_c": settings.gpu_abort_temperature_c,
        "gpu_abort_temperature_sustain_seconds": settings.gpu_abort_temperature_sustain_seconds,
        "gpu_emergency_temperature_c": settings.gpu_emergency_temperature_c,
        "gpu_cooldown_max_wait_seconds": settings.gpu_cooldown_max_wait_seconds,
        "gpu_resume_temperature_c": settings.gpu_resume_temperature_c,
        "gpu_minimum_free_vram_mb": settings.gpu_minimum_free_vram_mb,
        "gpu_runtime_minimum_free_vram_mb": settings.gpu_runtime_minimum_free_vram_mb,
        "gpu_maximum_utilization_percent": settings.gpu_maximum_utilization_percent,
        "gpu_maximum_encoder_utilization_percent": settings.gpu_maximum_encoder_utilization_percent,
    }


def _threshold(settings: GenerationSettings | None, field: str, default: int) -> int:
    if settings is None:
        return default
    value = getattr(settings, field, None)
    return int(value) if value is not None else default
