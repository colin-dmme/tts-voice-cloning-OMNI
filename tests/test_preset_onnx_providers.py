from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from omni_tts_core.engines.base import TtsEngineRequest
from omni_tts_core.engines.preset_onnx_engine import PresetOnnxSubprocessEngine
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.provider_options import normalize_provider_options
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.service import _validate_request_for_model
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest


class PresetOnnxCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ModelRegistry()

    def test_kokoro_catalog_is_multivoice_and_explicitly_sourced(self) -> None:
        spec = self.registry.get("kokoro_82m_v1_timestamped_onnx")
        self.assertEqual(spec.provider, "kokoro_onnx")
        self.assertEqual(len(spec.voice_presets), 54)
        self.assertEqual(spec.catalog_info["origin"], "community")
        self.assertEqual(
            spec.catalog_info["source_repo"],
            "onnx-community/Kokoro-82M-v1.0-ONNX-timestamped",
        )
        self.assertNotIn("vi", spec.capabilities.supported_languages)

    def test_supertonic_catalog_has_official_voices_and_languages(self) -> None:
        spec = self.registry.get("supertonic_3_official_onnx")
        self.assertEqual(spec.provider, "supertonic")
        self.assertEqual(len(spec.voice_presets), 10)
        self.assertEqual(len(spec.capabilities.supported_languages), 31)
        self.assertIn("vi", spec.capabilities.supported_languages)
        self.assertEqual(spec.catalog_info["origin"], "official")

    def test_provider_options_are_declared_and_validated_from_metadata(self) -> None:
        kokoro = provider_descriptor("kokoro_onnx")
        supertonic = provider_descriptor("supertonic")
        assert kokoro is not None and supertonic is not None
        self.assertEqual(
            normalize_provider_options(kokoro, {}),
            {"trim_silence": True, "continuous_prosody": False},
        )
        self.assertEqual(
            normalize_provider_options(supertonic, {"total_steps": 12}),
            {"total_steps": 12},
        )
        with self.assertRaises(ValueError):
            normalize_provider_options(supertonic, {"total_steps": 13})
        with self.assertRaises(ValueError):
            normalize_provider_options(supertonic, {"made_up": True})

    def test_request_validation_uses_provider_metadata(self) -> None:
        spec = self.registry.get("supertonic_3_official_onnx")
        valid = GenerateSpeechRequest(
            text="Xin chào",
            model_id=spec.model_id,
            language="vi",
            voice_source_mode="fixed",
            speaker_id="M1",
            speed=1.0,
        )
        _validate_request_for_model(valid, spec)
        self.assertEqual(valid.provider_options, {"total_steps": 8})
        invalid_speed = valid.model_copy(update={"speed": 0.6})
        with self.assertRaises(ConfigError):
            _validate_request_for_model(invalid_speed, spec)

    def test_settings_round_trip_keeps_provider_option_bag(self) -> None:
        settings = GenerationSettings(
            model_id="supertonic_3_official_onnx",
            provider_options={"total_steps": 10},
        )
        restored = GenerationSettings.from_preferences(settings.to_preferences())
        self.assertEqual(restored.provider_options, {"total_steps": 10})
        self.assertEqual(
            restored.to_request("hello").provider_options,
            {"total_steps": 10},
        )


class PresetOnnxEngineContractTest(unittest.TestCase):
    def test_engine_builds_generic_payload_and_reports_audio(self) -> None:
        spec = ModelRegistry().get("supertonic_3_official_onnx")
        engine = PresetOnnxSubprocessEngine(spec)
        captured: dict = {}

        def fake_run(payload, **_kwargs) -> None:
            captured.update(payload)
            for chunk in payload["chunks"]:
                sf.write(chunk["output_path"], np.zeros(400, dtype=np.float32), 24000)

        engine.worker.run = fake_run  # type: ignore[method-assign]
        result = engine.generate(
            TtsEngineRequest(
                text="Xin chào, bạn khỏe không?",
                language="vi",
                reference_audio_path=None,
                reference_text=None,
                speaker_id="M1",
                speed=1.0,
                pitch_shift=0.0,
                punctuation_pause_enabled=True,
                comma_pause_ms=90,
                sentence_pause_ms=320,
                clause_pause_ms=180,
                ellipsis_pause_ms=450,
                provider_options={"total_steps": 10},
            )
        )
        self.assertEqual(result.sample_rate, 24000)
        self.assertEqual(captured["options"], {"total_steps": 10})
        self.assertEqual(captured["speaker_id"], "M1")
        self.assertTrue(captured["chunks"][0]["segments"])


class RequiredArtifactsTest(unittest.TestCase):
    def test_required_files_participate_in_installation_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.onnx").write_bytes(b"model")
            (root / "config.json").write_text("{}", encoding="utf-8")
            spec = ModelSpec(
                model_id="fixture",
                display_name="Fixture",
                provider="fixture",
                model_type="tts",
                local_path=root,
                hf_repo="fixture/repo",
                language_priority="en",
                runtime={
                    "model_file": "model.onnx",
                    "config_file": "config.json",
                    "required_files": ["voices/F1.json"],
                },
            )
            self.assertFalse(ModelStorage().is_installed(spec))
            (root / "voices").mkdir()
            (root / "voices/F1.json").write_text("{}", encoding="utf-8")
            self.assertTrue(ModelStorage().is_installed(spec))


if __name__ == "__main__":
    unittest.main()
