from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_core.model_storage import ModelStorage
from omni_tts_core.provider_options import normalize_provider_options
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_core.service import _chunks_for_provider, _validate_request_for_model
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.schemas import GenerateSpeechRequest


def _load_worker_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "engines"
        / "zerotts_worker"
        / "synthesize.py"
    )
    spec = importlib.util.spec_from_file_location("omni_zerotts_worker_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ZeroTtsCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ModelRegistry()

    def test_catalog_matches_official_release_contract(self) -> None:
        spec = self.registry.get("zerotts_202m_official")

        self.assertEqual(spec.provider, "zerotts")
        self.assertEqual(
            spec.runtime["hf_revision"], "8a0c3c29f6f047011f5cae02d0b14475a690be86"
        )
        self.assertEqual(spec.default_voice_preset, "maichi")
        self.assertEqual(len(spec.voice_presets), 9)
        self.assertIn("__unconditioned__", spec.voice_presets)
        self.assertEqual(spec.capabilities.supported_languages, ["vi"])
        self.assertFalse(spec.capabilities.supports_voice_profile)
        self.assertFalse(spec.capabilities.supports_reference_text)

    def test_all_provider_defaults_are_normalized(self) -> None:
        descriptor = provider_descriptor("zerotts")
        assert descriptor is not None

        values = normalize_provider_options(descriptor, {})
        self.assertEqual(
            set(values),
            {
                "normalize_vi_text",
                "normalize_punctuation",
                "clean_segment_punctuation",
                "max_chunk_sec",
                "segment_gap_seconds",
                "cfg_scale",
                "text_temperature",
                "text_topk",
                "audio_temperature",
                "audio_topk",
                "audio_topp",
                "audio_repetition_penalty",
                "min_frames",
                "max_frames",
                "eoa_extra_frames",
                "seed",
                "streaming_decoder",
                "first_chunk_frames",
                "max_chunk_frames",
                "intra_op_num_threads",
                "codec_intra_op_num_threads",
                "warmup",
            },
        )
        self.assertEqual(values["cfg_scale"], 1.0)
        self.assertEqual(values["audio_temperature"], 0.8)
        self.assertEqual(values["audio_topk"], 25)
        self.assertEqual(values["audio_topp"], 0.95)
        self.assertEqual(values["audio_repetition_penalty"], 1.2)
        self.assertEqual(values["eoa_extra_frames"], 1)
        self.assertEqual(values["intra_op_num_threads"], 4)
        self.assertTrue(values["normalize_vi_text"])
        self.assertTrue(values["streaming_decoder"])
        with self.assertRaises(ValueError):
            normalize_provider_options(descriptor, {"audio_topk": 201})

    def test_request_validation_and_settings_round_trip(self) -> None:
        spec = self.registry.get("zerotts_202m_official")
        request = GenerateSpeechRequest(
            text="Ngày 23/8/2024",
            model_id=spec.model_id,
            language="vi",
            voice_source_mode="fixed",
            speaker_id="maichi",
            provider_options={"seed": 42, "normalize_vi_text": False},
        )

        _validate_request_for_model(request, spec)
        self.assertEqual(request.provider_options["seed"], 42)
        self.assertFalse(request.provider_options["normalize_vi_text"])
        settings = GenerationSettings(
            model_id=spec.model_id,
            speaker_id="maichi",
            provider_options=request.provider_options,
        )
        restored = GenerationSettings.from_preferences(settings.to_preferences())
        self.assertEqual(restored.provider_options, request.provider_options)

    def test_core_preserves_raw_text_for_native_preprocessing(self) -> None:
        text = "Ngày 23/8/2024 lúc 15h30"

        self.assertEqual(
            _chunks_for_provider(
                text,
                "vi",
                60,
                provider="zerotts",
                chunk_join_mode="auto",
            ),
            [text],
        )

    def test_model_download_uses_pinned_revision(self) -> None:
        spec = self.registry.get("zerotts_202m_official")
        captured: dict = {}

        def fake_download(*, local_dir, **kwargs):
            captured.update(kwargs)
            destination = Path(local_dir)
            for relative in [
                spec.runtime["model_file"],
                spec.runtime["config_file"],
                *spec.runtime["required_files"],
            ]:
                path = destination / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            return str(destination)

        with tempfile.TemporaryDirectory() as directory:
            temp_spec = spec.__class__(
                **{**spec.__dict__, "local_path": Path(directory) / "ZeroTTS"}
            )

            class Registry:
                def get(self, _model_id):
                    return temp_spec

                def all(self):
                    return [temp_spec]

            storage = ModelStorage(Registry())
            with patch(
                "omni_tts_core.model_storage.snapshot_download",
                side_effect=fake_download,
            ):
                result = storage.download(temp_spec.model_id)

        self.assertTrue(result.installed)
        self.assertEqual(captured["revision"], spec.runtime["hf_revision"])


class ZeroTtsWorkerTest(unittest.TestCase):
    def test_worker_streaming_path_writes_audio_and_forwards_settings(self) -> None:
        worker = _load_worker_module()
        calls: list[dict] = []

        class FakeTts:
            sample_rate = 48000

            def synthesize_stream(self, text, **kwargs):
                calls.append({"text": text, **kwargs})
                yield np.full((1, 120), 0.1, dtype=np.float32)

        options = {
            "cfg_scale": 1.4,
            "text_temperature": 0.9,
            "text_topk": 40,
            "audio_temperature": 0.7,
            "audio_topk": 20,
            "audio_topp": 0.9,
            "audio_repetition_penalty": 1.25,
            "min_frames": 4,
            "max_frames": 100,
            "eoa_extra_frames": 2,
            "seed": 7,
            "streaming_decoder": True,
            "first_chunk_frames": 1,
            "max_chunk_frames": 8,
            "segment_gap_seconds": 0.01,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.wav"
            payload = {
                "model_root": directory,
                "language": "vi",
                "speaker_id": "maichi",
                "options": options,
                "chunks": [{"text": "raw", "output_path": str(output)}],
            }
            with (
                patch.object(worker, "_load_model", return_value=FakeTts()),
                patch.object(worker, "_prepare_segments", return_value=["một", "hai"]),
            ):
                worker._synthesize(payload)
            audio, sample_rate = sf.read(output, dtype="float32")

        self.assertEqual(sample_rate, 48000)
        self.assertEqual(audio.shape[0], 120 + 480 + 120)
        self.assertEqual([item["text"] for item in calls], ["một", "hai"])
        self.assertEqual(calls[0]["voice"], "maichi")
        self.assertEqual(
            {key: calls[0][key] for key in calls[0] if key not in {"text", "voice"}},
            {
                "cfg_scale": 1.4,
                "text_temperature": 0.9,
                "text_topk": 40,
                "audio_temperature": 0.7,
                "audio_topk": 20,
                "audio_topp": 0.9,
                "audio_repetition_penalty": 1.25,
                "min_frames": 4,
                "max_frames": 100,
                "eoa_extra_frames": 2,
                "first_chunk_frames": 1,
                "max_chunk_frames": 8,
            },
        )

    def test_unconditioned_voice_disables_cfg(self) -> None:
        worker = _load_worker_module()

        class FakeTts:
            def synthesize(self, _text, **kwargs):
                self.kwargs = kwargs
                return np.ones((1, 20), dtype=np.float32)

        tts = FakeTts()
        audio = worker._synthesize_segment(
            tts,
            "xin chào",
            None,
            {"streaming_decoder": False, "cfg_scale": 3.0},
        )

        self.assertEqual(audio.size, 20)
        self.assertEqual(tts.kwargs["cfg_scale"], 1.0)


if __name__ == "__main__":
    unittest.main()
