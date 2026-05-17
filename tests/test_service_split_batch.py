from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.engines.base import TtsEngineResult
from omni_tts_core.model_registry import ModelSpec
from omni_tts_core.service import TtsService
from omni_tts_shared.schemas import GenerateSpeechRequest, ModelCapabilities


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


class RecordingEngine:
    def __init__(self) -> None:
        self.batch_calls = []
        self.generate_calls = 0

    def generate(self, request):
        self.generate_calls += 1
        raise AssertionError("split output should use generate_batch")

    def generate_batch(self, requests):
        self.batch_calls.append(list(requests))
        results = []
        for index, _request in enumerate(requests, start=1):
            audio = np.full(240, index / 10, dtype=np.float32)
            results.append(TtsEngineResult(audio=audio, sample_rate=24000))
        return results


class SplitBatchServiceTest(unittest.TestCase):
    def test_split_source_file_batches_all_chunks_before_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sample.srt"
            source.write_text(
                "\n\n".join(
                    [
                        "1\n00:00:00,000 --> 00:00:01,000\nHello world.",
                        (
                            "2\n00:00:01,000 --> 00:00:02,000\n"
                            "This sentence is intentionally long, with a comma break "
                            "that should split into two parts for the batch test."
                        ),
                        "3\n00:00:02,000 --> 00:00:03,000\nDone.",
                    ]
                ),
                encoding="utf-8",
            )
            spec = ModelSpec(
                model_id="fake_qwen",
                display_name="Fake Qwen",
                provider="qwen",
                model_type="tts",
                local_path=root / "model",
                hf_repo="fake/qwen",
                language_priority="multilingual",
                capabilities=ModelCapabilities(supported_languages=["vi"]),
            )
            service = TtsService(
                settings=DummySettings(root),
                registry=FakeRegistry(spec),
                storage=FakeStorage(),
            )
            engine = RecordingEngine()
            service._engines[spec.model_id] = engine

            request = GenerateSpeechRequest(
                text="file input",
                language="vi",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                max_chunk_chars=60,
                output_mode="split",
                output_srt=True,
            )

            result = service.generate_from_source_file(source, request, output_dir=root)

            self.assertEqual(engine.generate_calls, 0)
            self.assertEqual(len(engine.batch_calls), 1)
            batch_requests = engine.batch_calls[0]
            self.assertGreater(len(batch_requests), len(result.item_audio_paths))
            self.assertEqual(len(result.item_audio_paths), 3)
            self.assertEqual(len(result.item_srt_paths), 3)
            self.assertTrue(all(path.exists() for path in result.item_audio_paths))
            self.assertTrue(result.item_audio_paths[1].name.endswith("_002.wav"))
            second_chunk_count = len(batch_requests) - 2
            second_info = sf.info(str(result.item_audio_paths[1]))
            self.assertEqual(second_info.frames, 240 * second_chunk_count + 2400 * (second_chunk_count - 1))
            self.assertIn(f"{second_chunk_count}\n", result.item_srt_paths[1].read_text())


if __name__ == "__main__":
    unittest.main()
