from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from omni_tts_core.gpu_safety import (
    GpuSafetyConfig,
    GpuSafetyGuard,
    GpuSnapshot,
    is_fatal_cuda_error,
    parse_nvidia_temperature_limits,
)
from omni_tts_shared.errors import GpuSafetyError
from omni_tts_shared.schemas import GenerateSpeechRequest


def _snapshot(*, temp: int = 60, gpu: int = 0, encoder: int = 0, free: int = 9000) -> GpuSnapshot:
    return GpuSnapshot(
        timestamp="2026-07-22T10:00:00",
        name="Test GPU",
        driver_version="1.0",
        temperature_c=temp,
        gpu_utilization_percent=gpu,
        encoder_utilization_percent=encoder,
        memory_total_mb=11264,
        memory_used_mb=11264 - free,
        memory_free_mb=free,
    )


class _FakeProcessControl:
    def __init__(self) -> None:
        self.suspend_count = 0
        self.resume_count = 0

    def suspend(self) -> None:
        self.suspend_count += 1

    def resume(self) -> None:
        self.resume_count += 1


class GpuSafetyGuardTest(unittest.TestCase):
    def test_waits_for_multiple_safe_samples(self) -> None:
        samples = iter(
            [
                _snapshot(temp=83, encoder=30),
                _snapshot(temp=72),
                _snapshot(temp=71),
            ]
        )
        messages = []
        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(poll_seconds=0.001, safe_samples_required=2),
                snapshot_reader=lambda: next(samples),
                log_path=Path(temp) / "gpu.jsonl",
            )

            result = guard.wait_until_safe(None, messages.append)

        self.assertEqual(result.temperature_c, 71)
        self.assertTrue(any("NVENC" in message for message in messages))

    def test_runtime_temperature_limit_stops_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    abort_temperature_c=82,
                    abort_temperature_sustain_seconds=0.0,
                    poll_seconds=0.001,
                ),
                snapshot_reader=lambda: _snapshot(temp=82),
                log_path=Path(temp) / "gpu.jsonl",
            )

            with self.assertRaises(GpuSafetyError):
                guard.check_runtime()

    def test_temperature_spike_resets_before_sustained_stop(self) -> None:
        temperatures = iter([83, 81, 83, 83, 83])
        now = [0.0]
        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    abort_temperature_c=82,
                    abort_temperature_sustain_seconds=5.0,
                    poll_seconds=0.001,
                ),
                snapshot_reader=lambda: _snapshot(temp=next(temperatures)),
                log_path=Path(temp) / "gpu.jsonl",
                clock=lambda: now[0],
            )

            self.assertIsNotNone(guard.check_runtime())
            now[0] = 2.0
            self.assertIsNotNone(guard.check_runtime())
            now[0] = 6.0
            self.assertIsNotNone(guard.check_runtime())
            now[0] = 10.0
            self.assertIsNotNone(guard.check_runtime())
            now[0] = 11.1
            with self.assertRaises(GpuSafetyError):
                guard.check_runtime()

    def test_emergency_temperature_stops_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    abort_temperature_c=82,
                    abort_temperature_sustain_seconds=120.0,
                ),
                snapshot_reader=lambda: _snapshot(temp=90),
                log_path=Path(temp) / "gpu.jsonl",
            )

            with self.assertRaises(GpuSafetyError):
                guard.check_runtime()

    def test_emergency_temperature_is_user_configurable(self) -> None:
        temperatures = iter([90, 95])
        now = [0.0]
        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    abort_temperature_c=82,
                    abort_temperature_sustain_seconds=120.0,
                    emergency_temperature_c=95,
                    poll_seconds=0.001,
                ),
                snapshot_reader=lambda: _snapshot(temp=next(temperatures)),
                log_path=Path(temp) / "gpu.jsonl",
                clock=lambda: now[0],
            )

            self.assertIsNotNone(guard.check_runtime())
            now[0] = 1.0
            with self.assertRaises(GpuSafetyError):
                guard.check_runtime()

    def test_runtime_issue_pauses_then_resumes_with_exponential_backoff(self) -> None:
        samples = iter(
            [
                _snapshot(temp=67, free=649),
                _snapshot(temp=70, free=650),
                _snapshot(temp=70, free=900),
            ]
        )
        now = [0.0]
        waits = []

        def wait(seconds, _cancel_event) -> None:
            waits.append(seconds)
            now[0] += seconds

        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    runtime_minimum_free_vram_mb=700,
                    cooldown_initial_wait_seconds=10.0,
                    cooldown_max_wait_seconds=300.0,
                    poll_seconds=0.001,
                ),
                snapshot_reader=lambda: next(samples),
                log_path=Path(temp) / "gpu.jsonl",
                clock=lambda: now[0],
                waiter=wait,
            )
            control = _FakeProcessControl()

            result = guard.check_runtime_with_cooldown(control, None)

        self.assertEqual(waits, [10.0, 20.0])
        self.assertEqual(control.suspend_count, 1)
        self.assertEqual(control.resume_count, 1)
        self.assertEqual(result.memory_free_mb, 900)

    def test_runtime_cooldown_times_out_at_user_limit(self) -> None:
        now = [0.0]
        waits = []

        def wait(seconds, _cancel_event) -> None:
            waits.append(seconds)
            now[0] += seconds

        with tempfile.TemporaryDirectory() as temp:
            guard = GpuSafetyGuard(
                GpuSafetyConfig(
                    runtime_minimum_free_vram_mb=700,
                    cooldown_initial_wait_seconds=10.0,
                    cooldown_max_wait_seconds=25.0,
                    poll_seconds=0.001,
                ),
                snapshot_reader=lambda: _snapshot(temp=67, free=649),
                log_path=Path(temp) / "gpu.jsonl",
                clock=lambda: now[0],
                waiter=wait,
            )
            control = _FakeProcessControl()

            with self.assertRaisesRegex(GpuSafetyError, "25 giây"):
                guard.check_runtime_with_cooldown(control, None)

        self.assertEqual(waits, [10.0, 15.0])
        self.assertEqual(control.suspend_count, 1)
        self.assertEqual(control.resume_count, 1)

    def test_cuda_device_loss_markers_are_fatal(self) -> None:
        self.assertTrue(is_fatal_cuda_error("cuFFT error: CUFFT_INTERNAL_ERROR"))
        self.assertTrue(is_fatal_cuda_error("worker không thấy torch.cuda"))
        self.assertFalse(is_fatal_cuda_error("Audio prompt must be longer than 5 seconds"))

    def test_manual_values_override_model_runtime(self) -> None:
        config = GpuSafetyConfig.from_runtime(
            {"gpu_minimum_free_vram_mb": 6000, "gpu_abort_temperature_c": 82},
            {"gpu_minimum_free_vram_mb": 5000, "gpu_abort_temperature_c": 80},
        )

        self.assertEqual(config.minimum_free_vram_mb, 5000)
        self.assertEqual(config.abort_temperature_c, 80)

    def test_reads_temperature_limits_reported_by_driver(self) -> None:
        limits = parse_nvidia_temperature_limits(
            """
            GPU Shutdown Temp : 96 C
            GPU Slowdown Temp : 93 C
            GPU Target Temperature : 84 C
            """
        )

        self.assertEqual(limits.target_c, 84)
        self.assertEqual(limits.slowdown_c, 93)
        self.assertEqual(limits.shutdown_c, 96)

    def test_rejects_unsafe_temperature_relationships(self) -> None:
        with self.assertRaises(ValidationError):
            GenerateSpeechRequest(
                text="hello",
                gpu_start_temperature_c=84,
                gpu_abort_temperature_c=82,
            )
        with self.assertRaises(ValidationError):
            GenerateSpeechRequest(
                text="hello",
                gpu_abort_temperature_c=82,
                gpu_emergency_temperature_c=80,
            )
        request = GenerateSpeechRequest(text="hello", gpu_emergency_temperature_c=96)
        self.assertEqual(request.gpu_emergency_temperature_c, 96)


if __name__ == "__main__":
    unittest.main()
