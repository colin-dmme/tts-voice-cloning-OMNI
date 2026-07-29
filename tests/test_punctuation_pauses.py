from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

from omni_tts_core.service import _chunk_pause_values, _paragraph_pause_values
from omni_tts_core.text.punctuation_pauses import (
    PauseRange,
    PunctuationPauseConfig,
    pause_after_text,
    split_with_punctuation_pauses,
)
from omni_tts_shared.schemas import GenerateSpeechRequest


class _Spec:
    def __init__(self, provider: str) -> None:
        self.provider = provider


class PunctuationSplitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = PunctuationPauseConfig(
            sentence_ms=320,
            comma_ms=90,
            clause_ms=180,
            ellipsis_ms=450,
        )

    def test_splits_every_supported_category_and_preserves_marks(self) -> None:
        result = split_with_punctuation_pauses(
            "Một, hai; ba: bốn... Năm! Sáu?",
            self.config,
        )
        self.assertEqual(
            [(item.text, item.pause_after_ms) for item in result],
            [
                ("Một,", 90),
                ("hai;", 180),
                ("ba:", 180),
                ("bốn...", 450),
                ("Năm!", 320),
                ("Sáu?", 0),
            ],
        )

    def test_decimal_numbers_are_not_split(self) -> None:
        result = split_with_punctuation_pauses(
            "Giá trị 3.14 và 2,50. Xong.",
            self.config,
        )
        self.assertEqual([item.text for item in result], ["Giá trị 3.14 và 2,50.", "Xong."])

    def test_closing_quote_stays_with_previous_sentence(self) -> None:
        result = split_with_punctuation_pauses('Anh nói: “Được rồi!” Sau đó đi.', self.config)
        self.assertEqual(result[-2].text, "“Được rồi!”")
        self.assertEqual(result[-2].pause_after_ms, 320)

    def test_terminal_pause_classifier(self) -> None:
        self.assertEqual(pause_after_text("Xin chào,", self.config), 90)
        self.assertEqual(pause_after_text('“Được rồi!”', self.config), 320)
        self.assertEqual(pause_after_text("một ý chưa hết", self.config), None)

    def test_enabled_ranges_sample_each_punctuation_type(self) -> None:
        class _MaximumRng:
            @staticmethod
            def randint(_minimum: int, maximum: int) -> int:
                return maximum

        config = PunctuationPauseConfig(
            sentence_ms=320,
            comma_ms=90,
            sentence_range=PauseRange(280, 390),
            comma_range=PauseRange(70, 130),
        )
        result = split_with_punctuation_pauses(
            "Một, hai! Xong", config, _MaximumRng()
        )
        self.assertEqual(
            [(item.text, item.pause_after_ms) for item in result],
            [("Một,", 130), ("hai!", 390), ("Xong", 0)],
        )

    def test_disabled_ranges_keep_legacy_fixed_values(self) -> None:
        self.assertEqual(pause_after_text("Xin chào,", self.config), 90)

    def test_final_sentence_before_paragraph_boundary_has_no_own_silence(self) -> None:
        result = split_with_punctuation_pauses("Kết thúc đoạn.", self.config)
        self.assertEqual(
            [(item.text, item.pause_after_ms) for item in result],
            [("Kết thúc đoạn.", 0)],
        )


class CoreChunkPauseTest(unittest.TestCase):
    def test_request_rejects_an_inverted_random_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "sentence_pause_min_ms"):
            GenerateSpeechRequest(
                text="x",
                sentence_pause_min_ms=500,
                sentence_pause_max_ms=200,
            )

    def test_request_rejects_an_inverted_paragraph_random_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "paragraph_pause_min_ms"):
            GenerateSpeechRequest(
                text="x",
                paragraph_pause_min_ms=700,
                paragraph_pause_max_ms=500,
            )

    def test_paragraph_random_samples_once_per_boundary(self) -> None:
        class _MaximumRng:
            @staticmethod
            def randint(_minimum: int, maximum: int) -> int:
                return maximum

        request = GenerateSpeechRequest(
            text="x",
            paragraph_pause_random_enabled=True,
            paragraph_pause_min_ms=250,
            paragraph_pause_max_ms=350,
        )
        self.assertEqual(
            _paragraph_pause_values(request, 4, _MaximumRng()),
            [350, 350, 350],
        )

    def test_paragraph_fixed_mode_keeps_legacy_value(self) -> None:
        request = GenerateSpeechRequest(
            text="x",
            paragraph_pause_ms=280,
            paragraph_pause_random_enabled=False,
            paragraph_pause_min_ms=100,
            paragraph_pause_max_ms=900,
        )
        self.assertEqual(_paragraph_pause_values(request, 3), [280, 280])

    def test_piper_uses_terminal_punctuation_at_chunk_boundaries(self) -> None:
        request = GenerateSpeechRequest(
            text="x",
            model_id="piper",
            chunk_pause_ms=120,
            sentence_pause_ms=320,
            comma_pause_ms=90,
            clause_pause_ms=180,
            ellipsis_pause_ms=450,
        )
        pauses = _chunk_pause_values(
            request,
            _Spec("piper"),
            ["Một,", "Hai.", "Ba chưa hết", "Bốn."],
        )
        self.assertEqual(pauses, [90, 320, 120])

    def test_other_providers_only_use_visible_chunk_pause(self) -> None:
        request = GenerateSpeechRequest(
            text="x",
            chunk_pause_ms=120,
            sentence_pause_ms=999,
            comma_pause_ms=888,
        )
        pauses = _chunk_pause_values(
            request,
            _Spec("vieneu"),
            ["Một,", "Hai.", "Ba."],
        )
        self.assertEqual(pauses, [120, 120])

    def test_disabling_punctuation_falls_back_to_chunk_pause(self) -> None:
        request = GenerateSpeechRequest(
            text="x",
            punctuation_pause_enabled=False,
            chunk_pause_ms=77,
        )
        self.assertEqual(
            _chunk_pause_values(request, _Spec("piper"), ["Một.", "Hai."]),
            [77],
        )

    def test_chunk_boundary_random_pause_stays_inside_configured_range(self) -> None:
        request = GenerateSpeechRequest(
            text="x",
            model_id="piper",
            sentence_pause_random_enabled=True,
            sentence_pause_min_ms=275,
            sentence_pause_max_ms=325,
        )
        pauses = _chunk_pause_values(request, _Spec("piper"), ["Một.", "Hai."])
        self.assertGreaterEqual(pauses[0], 275)
        self.assertLessEqual(pauses[0], 325)


class _AudioChunk:
    sample_rate = 1000
    sample_width = 2
    sample_channels = 1
    audio_int16_bytes = bytes(100 * 2)


class _Voice:
    def synthesize(self, _text, syn_config=None):
        yield _AudioChunk()


class PiperWorkerSilenceTest(unittest.TestCase):
    def test_worker_writes_exact_pause_frames(self) -> None:
        worker_path = (
            Path(__file__).resolve().parents[1] / "engines" / "piper_worker" / "synthesize.py"
        )
        spec = importlib.util.spec_from_file_location("piper_worker_synthesize_test", worker_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "test.wav"
            with wave.open(str(output), "wb") as wav_file:
                module._synthesize_segments(
                    _Voice(),
                    [
                        {"text": "Một,", "pause_after_ms": 90},
                        {"text": "hai.", "pause_after_ms": 320},
                        {"text": "xong", "pause_after_ms": 0},
                    ],
                    wav_file,
                    object(),
                    fallback_sentence_pause_ms=320,
                )
            with wave.open(str(output), "rb") as wav_file:
                # 3 x 100 spoken frames + 90 + 320 silent frames.
                self.assertEqual(wav_file.getnframes(), 710)


if __name__ == "__main__":
    unittest.main()
