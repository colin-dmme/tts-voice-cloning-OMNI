from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.provider_options import (
    normalize_provider_options,
    provider_settings_for_model,
)
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.service import _validate_request_for_model
from omni_tts_core.worker_installation import base_installer_for_spec, worker_for_spec
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechRequest

GGUF_IDS = (
    "zerotts_202m_gguf_f32",
    "zerotts_202m_gguf_q8_0",
    "zerotts_202m_gguf_q4_0",
)


def _load_worker_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "engines"
        / "zerotts_gguf_worker"
        / "synthesize.py"
    )
    spec = importlib.util.spec_from_file_location("omni_zerotts_gguf_worker_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ZeroTtsGgufCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ModelRegistry()

    def test_all_official_gguf_variants_are_declared(self) -> None:
        expected_files = {
            "zerotts_202m_gguf_f32": "gguf/zerotts-f32.gguf",
            "zerotts_202m_gguf_q8_0": "gguf/zerotts-q8_0.gguf",
            "zerotts_202m_gguf_q4_0": "gguf/zerotts-q4_0.gguf",
        }
        zero_models = [
            item for item in self.registry.tts_models() if item.provider == "zerotts"
        ]

        self.assertEqual(len(zero_models), 4)
        for model_id, model_file in expected_files.items():
            spec = self.registry.get(model_id)
            self.assertEqual(
                spec.runtime["hf_revision"], "92ca8651645d4733df56620b3aadc768a76f7c46"
            )
            self.assertEqual(spec.runtime["model_file"], model_file)
            self.assertIn(model_file, spec.runtime["download_allow_patterns"])
            self.assertEqual(len(spec.voice_presets), 9)
            self.assertEqual(worker_for_spec(spec), "zerotts_gguf_worker")
            self.assertEqual(
                base_installer_for_spec(spec).name, "install_zerotts_gguf_worker.bat"
            )

    def test_gguf_contract_excludes_cfg_and_warmup(self) -> None:
        descriptor = provider_descriptor("zerotts")
        assert descriptor is not None
        spec = self.registry.get("zerotts_202m_gguf_q8_0")
        settings = provider_settings_for_model(descriptor, spec.runtime)
        keys = {item.key for item in settings}

        self.assertNotIn("cfg_scale", keys)
        self.assertNotIn("warmup", keys)
        self.assertIn("audio_temperature", keys)
        self.assertIn("intra_op_num_threads", keys)
        values = normalize_provider_options(descriptor, {}, settings=settings)
        self.assertEqual(set(values), keys)
        with self.assertRaises(ValueError):
            normalize_provider_options(
                descriptor, {"cfg_scale": 1.5}, settings=settings
            )

    def test_core_rejects_cfg_for_gguf_model(self) -> None:
        spec = self.registry.get("zerotts_202m_gguf_f32")
        request = GenerateSpeechRequest(
            text="Xin chào",
            model_id=spec.model_id,
            language="vi",
            voice_source_mode="fixed",
            speaker_id="maichi",
            provider_options={"cfg_scale": 1.5},
        )

        with self.assertRaises(ConfigError):
            _validate_request_for_model(request, spec)


class ZeroTtsGgufWorkerTest(unittest.TestCase):
    def test_worker_generates_codes_then_decodes_wav(self) -> None:
        worker = _load_worker_module()
        calls: list[dict] = []

        class FakeRuntime:
            def generate(self, **kwargs):
                calls.append(kwargs)
                return np.ones((1, 16, 3), dtype=np.int32)

        class FakeCodec:
            def decode(self, frames):
                self.frames = frames
                return np.full((1, 240), 0.2, dtype=np.float32)

        class FakeTokenizer:
            def __call__(self, _text):
                return np.asarray([1, 20, 2], dtype=np.int32)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.wav"
            payload = {
                "model_root": directory,
                "runtime": {"model_file": "gguf/zerotts-q8_0.gguf"},
                "language": "vi",
                "speaker_id": "maichi",
                "options": {
                    "seed": 42,
                    "streaming_decoder": False,
                    "audio_topk": 31,
                },
                "chunks": [{"text": "raw", "output_path": str(output)}],
            }
            with (
                patch.object(worker, "_load_runtime", return_value=FakeRuntime()),
                patch.object(worker, "_load_codec", return_value=FakeCodec()),
                patch.object(worker, "_load_tokenizer", return_value=FakeTokenizer()),
                patch.object(worker, "_voice_path", return_value=Path("voice.bin")),
                patch.object(worker, "_prepare_segments", return_value=["xin chào"]),
            ):
                worker._synthesize(payload)
            audio, sample_rate = sf.read(output, dtype="float32")

        self.assertEqual(sample_rate, 48_000)
        self.assertEqual(audio.shape, (240,))
        self.assertEqual(calls[0]["ids"], [1, 20, 2])
        self.assertEqual(calls[0]["options"]["audio_topk"], 31)


if __name__ == "__main__":
    unittest.main()
