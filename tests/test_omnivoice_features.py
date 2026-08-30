from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.engines import omnivoice_engine as oe
from omni_tts_core.engines.base import TtsEngineRequest
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.schemas import GenerateSpeechRequest


class NumStepSchemaTests(unittest.TestCase):
    def test_num_step_range_validation(self) -> None:
        self.assertEqual(
            GenerateSpeechRequest(text="hi", omnivoice_num_step=16).omnivoice_num_step, 16
        )
        with self.assertRaises(Exception):
            GenerateSpeechRequest(text="hi", omnivoice_num_step=0)
        with self.assertRaises(Exception):
            GenerateSpeechRequest(text="hi", omnivoice_num_step=200)


class SettingsStateTests(unittest.TestCase):
    def test_to_request_maps_num_step(self) -> None:
        settings = GenerationSettings(model_id="omnivoice_base", omnivoice_num_step=24)
        self.assertEqual(settings.to_request("hello").omnivoice_num_step, 24)

    def test_snapshot_round_trip_includes_num_step(self) -> None:
        restored = GenerationSettings.from_snapshot(
            GenerationSettings(omnivoice_num_step=12).to_snapshot()
        )
        self.assertEqual(restored.omnivoice_num_step, 12)


class EngineKwargTests(unittest.TestCase):
    class _FakeModel:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        def generate(self, **kwargs):
            self.kwargs = kwargs
            import numpy as np

            return [np.zeros(16, dtype="float32")]

    def _engine_with(self, model) -> oe.OmniVoiceEngine:
        engine = oe.OmniVoiceEngine.__new__(oe.OmniVoiceEngine)
        engine.spec = None
        engine._cache = None
        engine._models = {"stub": model}
        engine._load_model = lambda *_a, **_k: model  # type: ignore[assignment]
        return engine

    def test_num_step_forwarded_as_generation_config(self) -> None:
        model = self._FakeModel()
        engine = self._engine_with(model)
        # Isolate engine wiring from the real omnivoice runtime (app venv only).
        orig = oe._build_generation_config
        oe._build_generation_config = lambda n: {"num_step": n} if n else None
        try:
            engine.generate(
                TtsEngineRequest(
                    text="hi",
                    language="vi",
                    reference_audio_path=None,
                    reference_text=None,
                    speaker_id=None,
                    speed=1.0,
                    pitch_shift=0.0,
                    num_step=20,
                )
            )
        finally:
            oe._build_generation_config = orig
        self.assertEqual(model.kwargs.get("generation_config"), {"num_step": 20})
        self.assertNotIn("ref_audio", model.kwargs)


if __name__ == "__main__":
    unittest.main()
