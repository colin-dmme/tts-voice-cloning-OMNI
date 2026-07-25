from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

from omni_tts_core.service import _chunk_pause_values
from omni_tts_core.text.punctuation_pauses import (
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


class CoreChunkPauseTest(unittest.TestCase):
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
