from __future__ import annotations

import unittest
from pathlib import Path
from threading import Event

from omni_tts_core.app_controller import AppController, FileGenerationEvent
from omni_tts_core.file_queue import FileQueueStatus
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GpuSafetyError


class _FakeStatus:
    valid = True
    message = "OK"

    def feature_enabled(self, feature: str) -> bool:  # noqa: D401
        return True


class _FakeLicense:
    def get_status(self):
        return _FakeStatus()

    def current_device_id(self) -> str:
        return "device"

    def install_license(self, source_path: Path):
        return _FakeStatus()


class _FakeResult:
    def __init__(self, name: str) -> None:
        self.message = f"done {name}"
        self.job_dir = Path("outputs/jobs") / name


class _FakeJobStore:
    def __init__(self) -> None:
        self.saved: list[Path] = []

    def save_json(self, path: Path, payload) -> None:
        self.saved.append(path)


class _FakeService:
    def __init__(self, *, fail_on: set[str] | None = None, gpu_fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.gpu_fail_on = gpu_fail_on or set()
        self.job_store = _FakeJobStore()
        self.calls: list[str] = []

    def generate_from_source_file(self, source_path, request_template, output_dir, progress_callback, cancel_event):
        name = source_path.name
        self.calls.append(name)
        if name in self.gpu_fail_on:
            raise GpuSafetyError("GPU quá nóng")
        if name in self.fail_on:
            raise RuntimeError(f"lỗi {name}")
        return _FakeResult(name)


class _RecordingGate:
    def __init__(self) -> None:
        self.waits = 0

    def wait_before_generation(self, settings, cancel_event, status_callback) -> None:
        self.waits += 1


def _controller(service: _FakeService, gate=None) -> AppController:
    return AppController(service=service, license_provider=_FakeLicense(), safety_gate=gate)


def _tasks(*names: str) -> list[tuple[str, Path]]:
    return [(name, Path("input") / f"{name}.txt") for name in names]


class GenerateFilesTest(unittest.TestCase):
    def test_all_success_emits_done_and_saves_result(self) -> None:
        service = _FakeService()
        controller = _controller(service)
        events: list[FileGenerationEvent] = []
        outcomes = controller.generate_files(
            _tasks("a", "b"),
            GenerationSettings(),
            file_event_callback=events.append,
        )
        self.assertEqual([o.status for o in outcomes], [FileQueueStatus.DONE, FileQueueStatus.DONE])
        self.assertEqual(len(service.job_store.saved), 2)
        done = [e for e in events if e.status == FileQueueStatus.DONE]
        self.assertEqual(len(done), 2)

    def test_one_failure_continues_remaining(self) -> None:
        service = _FakeService(fail_on={"a.txt"})
        controller = _controller(service)
        outcomes = controller.generate_files(_tasks("a", "b"), GenerationSettings())
        statuses = [o.status for o in outcomes]
        self.assertEqual(statuses, [FileQueueStatus.FAILED, FileQueueStatus.DONE])
        self.assertEqual(service.calls, ["a.txt", "b.txt"])

    def test_gpu_safety_error_breaks_whole_queue(self) -> None:
        service = _FakeService(gpu_fail_on={"a.txt"})
        controller = _controller(service)
        outcomes = controller.generate_files(_tasks("a", "b"), GenerationSettings())
        self.assertEqual([o.status for o in outcomes], [FileQueueStatus.FAILED])
        self.assertEqual(service.calls, ["a.txt"])  # second file never attempted

    def test_safety_gate_called_before_each_file(self) -> None:
        service = _FakeService()
        gate = _RecordingGate()
        controller = _controller(service, gate=gate)
        controller.generate_files(_tasks("a", "b", "c"), GenerationSettings())
        self.assertEqual(gate.waits, 3)

    def test_empty_tasks_raise(self) -> None:
        controller = _controller(_FakeService())
        with self.assertRaises(Exception):
            controller.generate_files([], GenerationSettings())


if __name__ == "__main__":
    unittest.main()
