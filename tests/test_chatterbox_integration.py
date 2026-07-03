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
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelCapabilities, RefAudioHints


class _SingleModelRegistry:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def get(self, model_id: str) -> ModelSpec:
        return self.spec

    def all(self) -> list[ModelSpec]:
        return [self.spec]

    def tts_models(self) -> list[ModelSpec]:
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


class _DummySettings:
    app_name = "Test TTS"
    crossfade_ms = 0

    def __init__(self, root: Path) -> None:
        self.outputs_root = root / "jobs"


class _RecordingChatterboxModel:
    sr = 24000

    def __init__(self) -> None:
        self.kwargs = None

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return np.zeros(240, dtype=np.float32)


def _chatterbox_spec(root: Path) -> ModelSpec:
    return ModelSpec(
        model_id="fake_chatterbox",
        display_name="Fake Chatterbox",
        provider="chatterbox",
        model_type="tts",
        local_path=root / "model",
        hf_repo="ResembleAI/chatterbox-turbo",
        language_priority="en",
        capabilities=ModelCapabilities(
            supported_languages=["en"],
            supports_voice_profile=True,
            requires_voice_profile=True,
            supports_reference_text=False,
            supports_speed=False,
        ),
        runtime={
            "chatterbox_temperature": 0.8,
            "chatterbox_top_p": 0.95,
            "chatterbox_top_k": 1000,
            "chatterbox_repetition_penalty": 1.2,
            "chatterbox_norm_loudness": True,
        },
        ref_audio_hints=RefAudioHints(
            min_seconds=5.1,
            max_seconds=15.0,
            optimal_min_seconds=8.0,
            optimal_max_seconds=10.0,
            needs_transcript=False,
        ),
    )


class ChatterboxIntegrationTest(unittest.TestCase):
    def test_chatterbox_turbo_model_is_declared_as_non_default_test_model(self) -> None:
        spec = ModelRegistry().get("chatterbox_turbo_resembleai")

        self.assertEqual(spec.provider, "chatterbox")
        self.assertEqual(spec.hf_repo, "ResembleAI/chatterbox-turbo")
        self.assertFalse(spec.required)
        self.assertEqual(spec.catalog_info.get("risk"), "test")
        self.assertTrue(spec.capabilities.supports_voice_profile)
        self.assertTrue(spec.capabilities.requires_voice_profile)
        self.assertFalse(spec.capabilities.supports_reference_text)
        self.assertEqual(spec.capabilities.supported_languages, ["en"])
        self.assertGreater(spec.ref_audio_hints.min_seconds, 5.0)
        self.assertEqual(spec.runtime.get("chatterbox_temperature"), 0.8)

    def test_service_passes_chatterbox_settings_to_engine_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = _chatterbox_spec(root)
            service = TtsService(
                settings=_DummySettings(root),
                registry=_SingleModelRegistry(spec),
                storage=_FakeStorage(),
            )
            engine = _RecordingEngine()
            service._engines[spec.model_id] = engine

            request = GenerateSpeechRequest(
                text="Hello world.",
                language="en",
                model_id=spec.model_id,
                reference_audio_path=Path("ref.wav"),
                output_mode="merged",
                output_dir=root,
                output_stem="chatterbox",
                chatterbox_temperature=0.7,
                chatterbox_top_p=0.9,
                chatterbox_top_k=800,
                chatterbox_repetition_penalty=1.15,
                chatterbox_seed=1234,
                chatterbox_norm_loudness=False,
            )

            service.generate_audio(request)
            engine_request = engine.batch_calls[0][0]

            self.assertEqual(engine_request.chatterbox_temperature, 0.7)
            self.assertEqual(engine_request.chatterbox_top_p, 0.9)
            self.assertEqual(engine_request.chatterbox_top_k, 800)
            self.assertEqual(engine_request.chatterbox_repetition_penalty, 1.15)
            self.assertEqual(engine_request.chatterbox_seed, 1234)
            self.assertFalse(engine_request.chatterbox_norm_loudness)

    def test_service_rejects_chatterbox_without_voice_profile_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = _chatterbox_spec(root)
            service = TtsService(
                settings=_DummySettings(root),
                registry=_SingleModelRegistry(spec),
                storage=_FakeStorage(),
            )
            service._engines[spec.model_id] = _RecordingEngine()

            request = GenerateSpeechRequest(
                text="Hello world.",
                language="en",
                model_id=spec.model_id,
                output_mode="merged",
                output_dir=root,
            )

            with self.assertRaises(ConfigError):
                service.generate_audio(request)

    def test_worker_passes_turbo_generation_settings(self) -> None:
        worker_path = Path(__file__).resolve().parents[1] / "engines" / "chatterbox_worker" / "synthesize.py"
        spec = importlib.util.spec_from_file_location("chatterbox_worker_synthesize", worker_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        model = _RecordingChatterboxModel()
        with tempfile.TemporaryDirectory() as temp:
            output_path = Path(temp) / "out.wav"
            module._infer_to_file(
                model,
                {
                    "ref_audio": "ref.wav",
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 800,
                    "repetition_penalty": 1.15,
                    "seed": 1234,
                    "norm_loudness": False,
                },
                "hello",
                output_path,
            )

        self.assertEqual(model.kwargs["audio_prompt_path"], "ref.wav")
        self.assertEqual(model.kwargs["temperature"], 0.7)
        self.assertEqual(model.kwargs["top_p"], 0.9)
        self.assertEqual(model.kwargs["top_k"], 800)
        self.assertEqual(model.kwargs["repetition_penalty"], 1.15)
        self.assertFalse(model.kwargs["norm_loudness"])


if __name__ == "__main__":
    unittest.main()
