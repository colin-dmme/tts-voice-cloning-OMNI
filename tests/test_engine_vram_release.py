from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.service import TtsService
from omni_tts_shared.schemas import ModelCapabilities


class DummySettings:
    app_name = "Test TTS"
    crossfade_ms = 0

    def __init__(self, root: Path) -> None:
        self.outputs_root = root / "jobs"


class FakeRegistry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def get(self, model_id: str) -> ModelSpec:
        if model_id != self.spec.model_id:
            raise KeyError(model_id)
        return self.spec

    def all(self) -> list[ModelSpec]:
        return [self.spec]


class FakeStorage:
    def is_installed(self, spec: ModelSpec) -> bool:
        return True


class ClosableEngine:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class NoCloseEngine:
    """An engine without a close() method (e.g. a one-shot subprocess engine)."""


def _spec(model_id: str = "fake_qwen") -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        display_name="Fake Qwen",
        provider="qwen",
        model_type="tts",
        local_path=Path("model"),
        hf_repo="fake/qwen",
        language_priority="multilingual",
        capabilities=ModelCapabilities(supported_languages=["vi"]),
    )


class EngineReleaseTests(unittest.TestCase):
    def _service(self, root: Path) -> TtsService:
        spec = _spec()
        return TtsService(
            settings=DummySettings(root),
            registry=FakeRegistry(spec),
            storage=FakeStorage(),
        )

    def test_release_engines_closes_and_clears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(Path(tmp))
            engine_a = ClosableEngine()
            engine_b = ClosableEngine()
            service._engines["a"] = engine_a
            service._engines["b"] = engine_b

            released = service.release_engines()

            self.assertEqual(set(released), {"a", "b"})
            self.assertEqual(engine_a.closed, 1)
            self.assertEqual(engine_b.closed, 1)
            self.assertEqual(service.resident_models(), [])

    def test_release_engines_keeps_requested_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(Path(tmp))
            keep = ClosableEngine()
            drop = ClosableEngine()
            service._engines["keep"] = keep
            service._engines["drop"] = drop

            released = service.release_engines(keep_model_id="keep")

            self.assertEqual(released, ["drop"])
            self.assertEqual(drop.closed, 1)
            self.assertEqual(keep.closed, 0)
            self.assertEqual(service.resident_models(), ["keep"])

    def test_release_tolerates_engine_without_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(Path(tmp))
            service._engines["x"] = NoCloseEngine()

            released = service.release_engines()

            self.assertEqual(released, ["x"])
            self.assertEqual(service.resident_models(), [])

    def test_engine_for_unloads_other_models(self) -> None:
        """Requesting an engine frees any other resident model (unload on switch)."""
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(Path(tmp))
            other = ClosableEngine()
            wanted = ClosableEngine()
            service._engines["other_model"] = other
            service._engines["fake_qwen"] = wanted  # avoids the real factory

            returned = service._engine_for(_spec("fake_qwen"))

            self.assertIs(returned, wanted)
            self.assertEqual(other.closed, 1)
            self.assertEqual(wanted.closed, 0)
            self.assertEqual(service.resident_models(), ["fake_qwen"])


if __name__ == "__main__":
    unittest.main()
