from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from omni_tts_core.engines.base import TtsEngineRequest
from omni_tts_core.engines.piper_engine import PiperSubprocessEngine
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelCapabilities


class PiperTuningSchemaTest(unittest.TestCase):
    def test_defaults_preserve_previous_piper_behavior(self) -> None:
        request = GenerateSpeechRequest(text="Xin chào")
        self.assertEqual(request.piper_noise_scale, 0.667)
        self.assertEqual(request.piper_noise_w, 0.8)
        self.assertIsNone(request.piper_seed)

    def test_settings_round_trip_to_core_request(self) -> None:
        request = GenerationSettings(
            piper_noise_scale=0.9,
            piper_noise_w=0.65,
            piper_seed=3701,
        ).to_request("Xin chào")
        self.assertEqual(request.piper_noise_scale, 0.9)
        self.assertEqual(request.piper_noise_w, 0.65)
        self.assertEqual(request.piper_seed, 3701)

    def test_out_of_range_noise_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            GenerateSpeechRequest(text="Xin chào", piper_noise_scale=1.1)


class PiperEnginePayloadTest(unittest.TestCase):
    def test_engine_passes_tuning_values_to_worker_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = ModelSpec(
                model_id="piper_test",
                display_name="Piper Test",
                provider="piper",
                model_type="tts",
                local_path=root,
                hf_repo="",
                language_priority="vi",
                runtime={
                    "model_file": "voice.onnx",
                    "config_file": "voice.onnx.json",
                },
                capabilities=ModelCapabilities(),
            )
            captured: dict = {}

            def fake_run(_runtime, payload, **_kwargs) -> None:
                captured.update(payload)
                for item in payload["chunks"]:
                    with wave.open(item["output_path"], "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(22050)
                        wav_file.writeframes(bytes(200))

            request = TtsEngineRequest(
                text="Xin chào",
                language="vi",
                reference_audio_path=None,
                reference_text=None,
                speaker_id=None,
                speed=1.0,
                pitch_shift=0.0,
                piper_noise_scale=0.9,
                piper_noise_w=0.65,
                piper_seed=3701,
            )
            with (
                patch(
                    "omni_tts_core.engines.piper_engine._SHARED_PIPER_POOL.worker_runtime",
                    return_value=object(),
                ),
                patch(
                    "omni_tts_core.engines.piper_engine._SHARED_PIPER_POOL.run",
                    side_effect=fake_run,
                ),
            ):
                results = PiperSubprocessEngine(spec).generate_batch([request])

        self.assertEqual(len(results), 1)
        self.assertEqual(captured["noise_scale"], 0.9)
        self.assertEqual(captured["noise_w"], 0.65)
        self.assertEqual(captured["seed"], 3701)


if __name__ == "__main__":
    unittest.main()
