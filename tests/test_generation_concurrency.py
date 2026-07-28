from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

from omni_tts_core.generation_concurrency import GenerationCoordinator
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GenerationCancelled


@dataclass
class _Spec:
    provider: str


class _Registry:
    def get(self, model_id: str):
        return _Spec(
            "piper"
            if model_id.startswith("piper")
            else "chatterbox"
            if model_id.startswith("gpu")
            else "higgs_remote"
        )


@dataclass
class _RuntimeStatus:
    actual_device: str


class _Service:
    registry = _Registry()

    @staticmethod
    def runtime_status_for(model_id: str):
        return _RuntimeStatus("cuda" if model_id.startswith("gpu") else "cpu")


class GenerationCoordinatorTest(unittest.TestCase):
    def test_piper_allows_two_cpu_jobs_but_not_a_third(self) -> None:
        coordinator = GenerationCoordinator(_Service())
        settings = GenerationSettings(model_id="piper-a", runtime_target="cpu")
        release = Event()
        entered: list[int] = []

        def run(index: int) -> None:
            with coordinator.acquire(settings, None):
                entered.append(index)
                release.wait(2)

        threads = [Thread(target=run, args=(index,)) for index in range(3)]
        for thread in threads:
            thread.start()
        deadline = monotonic() + 1
        while len(entered) < 2 and monotonic() < deadline:
            sleep(0.01)

        self.assertEqual(len(entered), 2)
        release.set()
        for thread in threads:
            thread.join(2)
        self.assertEqual(sorted(entered), [0, 1, 2])

    def test_all_local_gpu_models_share_one_slot(self) -> None:
        coordinator = GenerationCoordinator(_Service())
        first = coordinator.resource_for(
            GenerationSettings(model_id="gpu-a", runtime_target="cuda")
        )
        second = coordinator.resource_for(
            GenerationSettings(model_id="gpu-b", runtime_target="cuda")
        )

        self.assertEqual(first.key, "local-gpu")
        self.assertEqual(second.key, "local-gpu")
        self.assertEqual(first.parallel_limit, 1)

    def test_same_output_stem_is_serialized_even_when_cpu_has_two_slots(self) -> None:
        coordinator = GenerationCoordinator(_Service())
        settings = GenerationSettings(
            model_id="piper-a",
            runtime_target="cpu",
            output_dir=Path("C:/outputs"),
            output_stem="same-name",
        )
        release = Event()
        entered: list[int] = []

        def run(index: int) -> None:
            with coordinator.acquire(settings, None):
                entered.append(index)
                release.wait(2)

        first = Thread(target=run, args=(1,))
        second = Thread(target=run, args=(2,))
        first.start()
        second.start()
        sleep(0.1)

        self.assertEqual(len(entered), 1)
        release.set()
        first.join(2)
        second.join(2)
        self.assertEqual(sorted(entered), [1, 2])

    def test_waiting_job_can_be_cancelled(self) -> None:
        coordinator = GenerationCoordinator(_Service())
        settings = GenerationSettings(model_id="gpu-a", runtime_target="cuda")
        cancel = Event()
        errors: list[Exception] = []

        with coordinator.acquire(settings, None):
            thread = Thread(
                target=lambda: self._try_acquire(
                    coordinator, settings, cancel, errors
                )
            )
            thread.start()
            sleep(0.1)
            cancel.set()
            thread.join(2)

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], GenerationCancelled)

    @staticmethod
    def _try_acquire(coordinator, settings, cancel, errors) -> None:
        try:
            with coordinator.acquire(settings, cancel):
                pass
        except Exception as error:
            errors.append(error)


if __name__ == "__main__":
    unittest.main()
