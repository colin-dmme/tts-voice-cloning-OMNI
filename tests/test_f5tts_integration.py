from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.model_registry import ModelRegistry, ModelSpec
from omni_tts_core.service import TtsService
from omni_tts_core.voice_profile_policy import VoiceProfilePolicy
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelCapabilities, RefAudioHints, VoiceProfile


class _SingleModelRegistry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def get(self, model_id: str) -> ModelSpec:
        return self.spec


class _FakeRegistry(_SingleModelRegistry):
    def all(self) -> list[ModelSpec]:
        return [self.spec]


class _FakeStorage:
    def is_installed(self, spec: ModelSpec) -> bool:
        return True


class _RecordingEngine:
    def __init__(self) -> None:
        self.batch_calls = []

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        self.batch_calls.append(list(requests))
        if progress_callback is not None:
            progress_callback(len(requests), len(requests))
        return [TtsEngineResult(audio=np.zeros(240, dtype=np.float32), sample_rate=24000) for _ in requests]


class _RecordingF5Model:
    def __init__(self) -> None:
        self.kwargs = None

    def infer(self, **kwargs):
        self.kwargs = kwargs
        return np.zeros(240, dtype=np.float32), 24000, None


class _DummySettings:
    app_name = "Test TTS"
    crossfade_ms = 0

    def __init__(self, root: Path) -> None:
        self.outputs_root = root / "jobs"


def _f5_spec(root: Path) -> ModelSpec:
    return ModelSpec(
        model_id="fake_f5",
        display_name="Fake F5",
        provider="f5tts",
        model_type="tts",
        local_path=root / "model",
        hf_repo="SWivid/F5-TTS",
        language_priority="en",
        capabilities=ModelCapabilities(
            supported_languages=["en"],
            supports_voice_profile=True,
            requires_voice_profile=True,
            supports_reference_text=True,
            supports_speed=True,
        ),
        ref_audio_hints=RefAudioHints(
            min_seconds=3.0,
            max_seconds=12.0,
            optimal_min_seconds=5.0,
            optimal_max_seconds=10.0,
            needs_transcript=True,
        ),
    )


class F5TtsIntegrationTest(unittest.TestCase):
    def test_f5tts_model_is_declared_as_non_default_test_model(self) -> None:
        spec = ModelRegistry().get("f5tts_v1_base_swivid")

        self.assertEqual(spec.provider, "f5tts")
        self.assertEqual(spec.hf_repo, "SWivid/F5-TTS")
        self.assertFalse(spec.required)
        self.assertEqual(spec.catalog_info.get("risk"), "test")
        self.assertTrue(spec.capabilities.supports_voice_profile)
        self.assertTrue(spec.capabilities.requires_voice_profile)
        self.assertTrue(spec.ref_audio_hints.needs_transcript)
        self.assertLessEqual(spec.ref_audio_hints.max_seconds, 12.0)
        self.assertEqual(spec.runtime.get("f5_nfe_step"), 32)

    def test_f5_policy_requires_reference_transcript(self) -> None:
        spec = _f5_spec(Path("root"))
        policy = VoiceProfilePolicy(_SingleModelRegistry(spec))
        profile = VoiceProfile(
            profile_id="voice-1",
            name="Voice 1",
            audio_path=Path("voice.wav"),
            transcript="",
            duration_seconds=6.0,
        )

        compat = policy.check_compatibility(profile, "fake_f5")

        self.assertEqual(compat.status, "warn")
        self.assertIn("transcript", compat.message)

    def test_service_passes_f5_settings_to_engine_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = _f5_spec(root)
            service = TtsService(
                settings=_DummySettings(root),
                registry=_FakeRegistry(spec),
                storage=_FakeStorage(),
            )
            engine = _RecordingEngine()
            service._engines[spec.model_id] = engine

            request = GenerateSpeechRequest(
                text="Hello world.",
                language="en",
                model_id=spec.model_id,
                reference_audio_path=Path("ref.wav"),
                reference_text="Reference text.",
                output_mode="merged",
                output_dir=root,
                output_stem="f5",
                f5_nfe_step=16,
                f5_cfg_strength=2.5,
                f5_sway_sampling_coef=-0.8,
                f5_cross_fade_duration=0.2,
                f5_target_rms=0.12,
                f5_remove_silence=True,
                f5_seed=1234,
                f5_fix_duration=4.5,
            )

            service.generate_audio(request)
            engine_request = engine.batch_calls[0][0]

            self.assertEqual(engine_request.f5_nfe_step, 16)
            self.assertEqual(engine_request.f5_cfg_strength, 2.5)
            self.assertEqual(engine_request.f5_sway_sampling_coef, -0.8)
            self.assertEqual(engine_request.f5_cross_fade_duration, 0.2)
            self.assertEqual(engine_request.f5_target_rms, 0.12)
            self.assertTrue(engine_request.f5_remove_silence)
            self.assertEqual(engine_request.f5_seed, 1234)
            self.assertEqual(engine_request.f5_fix_duration, 4.5)

    def test_service_rejects_f5_clone_without_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = _f5_spec(root)
            service = TtsService(
                settings=_DummySettings(root),
                registry=_FakeRegistry(spec),
                storage=_FakeStorage(),
            )
            service._engines[spec.model_id] = _RecordingEngine()

            request = GenerateSpeechRequest(
                text="Hello world.",
                language="en",
                model_id=spec.model_id,
                reference_audio_path=Path("ref.wav"),
                reference_text="",
                output_mode="merged",
                output_dir=root,
            )

            with self.assertRaises(ConfigError):
                service.generate_audio(request)

    def test_worker_disables_f5_progress_with_none(self) -> None:
        worker_path = Path(__file__).resolve().parents[1] / "engines" / "f5_worker" / "synthesize.py"
        spec = importlib.util.spec_from_file_location("f5_worker_synthesize", worker_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        model = _RecordingF5Model()
        with tempfile.TemporaryDirectory() as temp:
            output_path = Path(temp) / "out.wav"
            module._infer_to_file(
                model,
                {
                    "ref_audio": "ref.wav",
                    "ref_text": "Reference transcript.",
                    "speed": 1.0,
                    "nfe_step": 32,
                    "cfg_strength": 2.0,
                    "sway_sampling_coef": -1.0,
                    "cross_fade_duration": 0.15,
                    "target_rms": 0.1,
                },
                "hello",
                output_path,
            )

        self.assertIsNone(model.kwargs["progress"])


if __name__ == "__main__":
    unittest.main()
