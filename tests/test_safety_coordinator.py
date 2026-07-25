from __future__ import annotations

import time
import unittest

from omni_tts_core.hardware_monitor import HardwareSnapshot
from omni_tts_core.safety_coordinator import SafetyGate
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GpuSafetyError


class _FakeSpec:
    def __init__(self, provider: str, runtime: dict) -> None:
        self.provider = provider
        self.runtime = runtime


class _FakeRegistry:
    def __init__(self, spec: _FakeSpec) -> None:
        self._spec = spec

    def get(self, model_id: str) -> _FakeSpec:
        return self._spec


class _FakeRuntimeStatus:
    def __init__(self, actual_device: str) -> None:
        self.actual_device = actual_device


class _FakeService:
    def __init__(self, provider: str = "vieneu", actual_device: str = "auto-cuda", runtime: dict | None = None) -> None:
        self.registry = _FakeRegistry(_FakeSpec(provider, runtime or {}))
        self._actual_device = actual_device

    def runtime_status_for(self, model_id: str) -> _FakeRuntimeStatus:
        return _FakeRuntimeStatus(self._actual_device)


class _FakeProbe:
    def __init__(self, snapshots: list[HardwareSnapshot]) -> None:
        self._snapshots = snapshots
        self._index = 0

    def snapshot(self) -> HardwareSnapshot:
        snapshot = self._snapshots[min(self._index, len(self._snapshots) - 1)]
        self._index += 1
        return snapshot


def _snap(temp: float | None, free_mb: int = 9000) -> HardwareSnapshot:
    if temp is None:
        return HardwareSnapshot(timestamp=time.time(), error="no gpu")
    return HardwareSnapshot(
        timestamp=time.time(),
        gpu_name="Test",
        gpu_temperature_c=temp,
        gpu_utilization_percent=0.0,
        gpu_encoder_utilization_percent=0.0,
        gpu_memory_total_mb=11264,
        gpu_memory_used_mb=11264 - free_mb,
    )


class AppliesToTest(unittest.TestCase):
    def test_disabled_never_applies(self) -> None:
        gate = SafetyGate(_FakeService(), _FakeProbe([_snap(60)]))
        self.assertFalse(gate.applies_to(GenerationSettings(gpu_safety_enabled=False)))

    def test_cpu_target_skips(self) -> None:
        gate = SafetyGate(_FakeService(), _FakeProbe([_snap(60)]))
        self.assertFalse(gate.applies_to(GenerationSettings(runtime_target="cpu")))

    def test_cuda_target_applies(self) -> None:
        gate = SafetyGate(_FakeService(actual_device="auto-cpu"), _FakeProbe([_snap(60)]))
        self.assertTrue(gate.applies_to(GenerationSettings(runtime_target="cuda")))

    def test_auto_target_consults_resolved_device(self) -> None:
        cuda = SafetyGate(_FakeService(actual_device="auto-cuda"), _FakeProbe([_snap(60)]))
        self.assertTrue(cuda.applies_to(GenerationSettings(runtime_target="auto")))
        cpu = SafetyGate(_FakeService(actual_device="auto-cpu"), _FakeProbe([_snap(60)]))
        self.assertFalse(cpu.applies_to(GenerationSettings(runtime_target="auto")))


class AssessTest(unittest.TestCase):
    def test_levels(self) -> None:
        gate = SafetyGate(_FakeService(), _FakeProbe([_snap(60)]))
        settings = GenerationSettings(gpu_start_temperature_c=75, gpu_abort_temperature_c=82)
        self.assertEqual(gate.assess(_snap(60), settings).level, "ok")
        self.assertEqual(gate.assess(_snap(78), settings).level, "warning")
        self.assertEqual(gate.assess(_snap(85), settings).level, "hot")
        self.assertEqual(gate.assess(_snap(None), settings).level, "unavailable")

    def test_low_vram_warns(self) -> None:
        gate = SafetyGate(_FakeService(), _FakeProbe([_snap(60)]))
        settings = GenerationSettings(gpu_minimum_free_vram_mb=6000)
        assessment = gate.assess(_snap(60, free_mb=1000), settings)
        self.assertEqual(assessment.level, "warning")
        self.assertTrue(any("VRAM" in reason for reason in assessment.reasons))


class WaitBeforeGenerationTest(unittest.TestCase):
    _fast_runtime = {"gpu_poll_seconds": 0.5, "gpu_safe_samples_required": 1, "gpu_wait_timeout_seconds": 0.05}

    def test_noop_when_not_applicable(self) -> None:
        gate = SafetyGate(_FakeService(actual_device="auto-cpu"), _FakeProbe([_snap(None)]))
        gate.wait_before_generation(GenerationSettings(runtime_target="cpu"), None, None)  # no raise

    def test_skips_chatterbox(self) -> None:
        service = _FakeService(provider="chatterbox", runtime=self._fast_runtime)
        gate = SafetyGate(service, _FakeProbe([_snap(95)]))  # hot, but chatterbox self-guards
        gate.wait_before_generation(GenerationSettings(runtime_target="cuda"), None, None)  # no raise

    def test_passes_when_gpu_cool(self) -> None:
        service = _FakeService(provider="vieneu", runtime=self._fast_runtime)
        gate = SafetyGate(service, _FakeProbe([_snap(60)]))
        settings = GenerationSettings(runtime_target="cuda", gpu_start_temperature_c=75)
        gate.wait_before_generation(settings, None, None)  # no raise

    def test_raises_when_gpu_stays_hot(self) -> None:
        service = _FakeService(provider="vieneu", runtime=self._fast_runtime)
        gate = SafetyGate(service, _FakeProbe([_snap(95)]))
        settings = GenerationSettings(runtime_target="cuda", gpu_start_temperature_c=75)
        with self.assertRaises(GpuSafetyError):
            gate.wait_before_generation(settings, None, None)


if __name__ == "__main__":
    unittest.main()
