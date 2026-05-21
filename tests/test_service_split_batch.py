from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import subprocess
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

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        self.batch_calls.append(list(requests))
        results = []
        for index, _request in enumerate(requests, start=1):
            audio = np.full(240, index / 10, dtype=np.float32)
            results.append(TtsEngineResult(audio=audio, sample_rate=24000))
            if progress_callback is not None:
                progress_callback(index, len(requests))
        return results


class StreamingEngine:
    def __init__(self, root: Path, expected_first_output: Path) -> None:
        self.root = root
        self.expected_first_output = expected_first_output
        self.first_output_seen_before_return = False

    def generate(self, request):
        raise AssertionError("split output should use generate_batch")

    def generate_batch(self, requests, progress_callback=None, chunk_callback=None):
        chunk_dir = self.root / "chunks"
        chunk_dir.mkdir()
        results = []
        for index, _request in enumerate(requests):
            audio = np.full(240, (index + 1) / 10, dtype=np.float32)
            path = chunk_dir / f"chunk_{index:03d}.wav"
            sf.write(str(path), audio, 24000)
            if chunk_callback is not None:
                chunk_callback(index, path)
            if index == 0:
                self.first_output_seen_before_return = self.expected_first_output.exists()
            if progress_callback is not None:
                progress_callback(index + 1, len(requests))
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
                srt_file_padding_ms=500,
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
            self.assertEqual(result.item_srt_paths, [])
            self.assertIsNotNone(result.srt_path)
            self.assertTrue(result.srt_path.exists())
            self.assertTrue(all(path.exists() for path in result.item_audio_paths))
            self.assertTrue(result.item_audio_paths[1].name.endswith("_002.wav"))
            second_chunk_count = len(batch_requests) - 2
            second_info = sf.info(str(result.item_audio_paths[1]))
            self.assertEqual(second_info.frames, 240 * second_chunk_count + 2400 * (second_chunk_count - 1))
            srt_text = result.srt_path.read_text(encoding="utf-8")
            self.assertIn("2\n00:00:00,510 -->", srt_text)
            self.assertIn("This sentence is intentionally long", srt_text)

    def test_split_source_file_writes_completed_units_during_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stream.srt"
            source.write_text(
                "\n\n".join(
                    [
                        "1\n00:00:00,000 --> 00:00:01,000\nHello world.",
                        "2\n00:00:01,000 --> 00:00:02,000\nSecond line.",
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
            expected_first_output = root / "stream" / "stream_001.wav"
            engine = StreamingEngine(root, expected_first_output)
            service._engines[spec.model_id] = engine

            request = GenerateSpeechRequest(
                text="file input",
                language="vi",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                max_chunk_chars=80,
                output_mode="split",
                output_srt=False,
            )

            result = service.generate_from_source_file(source, request, output_dir=root)

            self.assertTrue(engine.first_output_seen_before_return)
            self.assertEqual(len(result.item_audio_paths), 2)
            self.assertTrue(expected_first_output.exists())

    def test_split_source_file_can_write_joined_audio_for_timeline_srt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "join.srt"
            source.write_text(
                "\n\n".join(
                    [
                        "1\n00:00:00,000 --> 00:00:01,000\nFirst line.",
                        "2\n00:00:01,000 --> 00:00:02,000\nSecond line.",
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
            expected_first_output = root / "join" / "join_001.wav"
            service._engines[spec.model_id] = StreamingEngine(root, expected_first_output)

            request = GenerateSpeechRequest(
                text="file input",
                language="vi",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                srt_file_padding_ms=500,
                max_chunk_chars=80,
                output_mode="split",
                output_srt=True,
                join_split_output_audio=True,
            )

            result = service.generate_from_source_file(source, request, output_dir=root)

            self.assertEqual(result.audio_path, root / "join" / "join.wav")
            self.assertEqual(len(result.item_audio_paths), 2)
            self.assertNotIn(result.audio_path, result.item_audio_paths)
            self.assertTrue(result.audio_path.exists())
            self.assertEqual(sf.info(str(result.audio_path)).frames, 240 + 12000 + 240)
            self.assertIsNotNone(result.srt_path)
            self.assertIn("2\n00:00:00,510 -->", result.srt_path.read_text(encoding="utf-8"))

    def test_merged_text_uses_paragraph_pause_between_blank_line_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = ModelSpec(
                model_id="fake_qwen",
                display_name="Fake Qwen",
                provider="qwen",
                model_type="tts",
                local_path=root / "model",
                hf_repo="fake/qwen",
                language_priority="multilingual",
                capabilities=ModelCapabilities(supported_languages=["en"]),
            )
            service = TtsService(
                settings=DummySettings(root),
                registry=FakeRegistry(spec),
                storage=FakeStorage(),
            )
            engine = RecordingEngine()
            service._engines[spec.model_id] = engine

            request = GenerateSpeechRequest(
                text="First paragraph.\n\nSecond paragraph.",
                language="en",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                paragraph_pause_ms=500,
                max_chunk_chars=80,
                output_mode="merged",
                output_dir=root,
                output_stem="merged_text",
                output_srt=True,
            )

            result = service.generate_audio(request)

            self.assertEqual(engine.generate_calls, 0)
            self.assertEqual(len(engine.batch_calls), 1)
            self.assertEqual(len(engine.batch_calls[0]), 2)
            self.assertEqual(result.audio_path, root / "merged_text.wav")
            self.assertEqual(sf.info(str(result.audio_path)).frames, 240 + 12000 + 240)
            self.assertIsNotNone(result.srt_path)
            self.assertIn("2\n00:00:00,510 -->", result.srt_path.read_text(encoding="utf-8"))

    def test_merged_source_file_uses_paragraph_pause_between_blank_line_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "article.txt"
            source.write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")
            spec = ModelSpec(
                model_id="fake_qwen",
                display_name="Fake Qwen",
                provider="qwen",
                model_type="tts",
                local_path=root / "model",
                hf_repo="fake/qwen",
                language_priority="multilingual",
                capabilities=ModelCapabilities(supported_languages=["en"]),
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
                language="en",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                paragraph_pause_ms=500,
                max_chunk_chars=80,
                output_mode="merged",
                output_srt=True,
            )

            result = service.generate_from_source_file(source, request, output_dir=root)

            self.assertEqual(engine.generate_calls, 0)
            self.assertEqual(len(engine.batch_calls), 1)
            self.assertEqual(result.audio_path, root / "article.wav")
            self.assertEqual(sf.info(str(result.audio_path)).frames, 240 + 12000 + 240)
            self.assertIsNotNone(result.srt_path)
            self.assertIn("2\n00:00:00,510 -->", result.srt_path.read_text(encoding="utf-8"))

    @unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg is required for MP3 export")
    def test_split_source_file_can_write_joined_mp3_for_timeline_srt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "join_mp3.srt"
            source.write_text(
                "\n\n".join(
                    [
                        "1\n00:00:00,000 --> 00:00:01,000\nFirst line.",
                        "2\n00:00:01,000 --> 00:00:02,000\nSecond line.",
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
            expected_first_output = root / "join_mp3" / "join_mp3_001.mp3"
            service._engines[spec.model_id] = StreamingEngine(root, expected_first_output)

            request = GenerateSpeechRequest(
                text="file input",
                language="vi",
                model_id=spec.model_id,
                sentence_pause_ms=100,
                srt_file_padding_ms=500,
                max_chunk_chars=80,
                output_mode="split",
                output_audio_format="mp3",
                mp3_bitrate_kbps=192,
                output_srt=True,
                join_split_output_audio=True,
            )

            result = service.generate_from_source_file(source, request, output_dir=root)

            self.assertEqual(result.audio_path, root / "join_mp3" / "join_mp3.mp3")
            self.assertTrue(result.audio_path.exists())
            self.assertEqual([path.suffix for path in result.item_audio_paths], [".mp3", ".mp3"])
            self.assertTrue(expected_first_output.exists())
            self.assertIsNotNone(result.srt_path)
            self.assertIn("2\n00:00:00,510 -->", result.srt_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(result.duration_seconds, 0.52)

            ffprobe = shutil.which("ffprobe")
            if ffprobe is not None:
                probe = subprocess.run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-select_streams",
                        "a:0",
                        "-show_entries",
                        "stream=codec_name,sample_rate,channels",
                        "-of",
                        "json",
                        str(result.audio_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(probe.returncode, 0, probe.stderr)
                stream = json.loads(probe.stdout)["streams"][0]
                self.assertEqual(stream["codec_name"], "mp3")
                self.assertEqual(stream["sample_rate"], "48000")
                self.assertEqual(stream["channels"], 1)


if __name__ == "__main__":
    unittest.main()
