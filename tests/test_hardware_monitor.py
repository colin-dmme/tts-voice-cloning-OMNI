from __future__ import annotations

import time
import unittest

from omni_tts_core.hardware_monitor import HardwareProbe, HardwareSnapshot, to_gpu_snapshot


def _gpu_snapshot(**overrides) -> HardwareSnapshot:
    base = dict(
        timestamp=time.time(),
        gpu_name="Test GPU",
        gpu_temperature_c=66.0,
        gpu_utilization_percent=2.0,
        gpu_encoder_utilization_percent=0.0,
        gpu_memory_total_mb=11264,
        gpu_memory_used_mb=6000,
        cpu_utilization_percent=22.0,
        ram_used_gb=35.0,
        ram_total_gb=64.0,
    )
    base.update(overrides)
    return HardwareSnapshot(**base)


class HardwareSnapshotTest(unittest.TestCase):
    def test_free_vram_computed(self) -> None:
        snapshot = _gpu_snapshot()
        self.assertEqual(snapshot.gpu_memory_free_mb, 11264 - 6000)
        self.assertTrue(snapshot.has_gpu)

    def test_no_gpu_snapshot(self) -> None:
        snapshot = HardwareSnapshot(timestamp=time.time(), error="Không tìm thấy nvidia-smi")
        self.assertIsNone(snapshot.gpu_memory_free_mb)
        self.assertFalse(snapshot.has_gpu)


class ToGpuSnapshotTest(unittest.TestCase):
    def test_converts_to_guard_snapshot(self) -> None:
        gpu = to_gpu_snapshot(_gpu_snapshot(gpu_temperature_c=81.6))
        self.assertEqual(gpu.temperature_c, 82)  # rounded
        self.assertEqual(gpu.memory_free_mb, 11264 - 6000)
        self.assertEqual(gpu.name, "Test GPU")

    def test_raises_when_no_gpu(self) -> None:
        snapshot = HardwareSnapshot(timestamp=time.time(), error="no gpu")
        with self.assertRaises(RuntimeError):
            to_gpu_snapshot(snapshot)


class ProbeCacheTest(unittest.TestCase):
    def test_snapshot_is_cached_within_window(self) -> None:
        probe = HardwareProbe(nvidia_smi="", cache_seconds=10.0)
        first = probe.snapshot()
        second = probe.snapshot()
        self.assertIs(first, second)  # cached instance reused

    def test_probe_never_raises_without_nvidia_smi(self) -> None:
        probe = HardwareProbe(nvidia_smi="", cache_seconds=0.0)
        snapshot = probe.snapshot()
        self.assertIsNotNone(snapshot.error)
        self.assertIsNotNone(snapshot.ram_total_gb)


if __name__ == "__main__":
    unittest.main()
