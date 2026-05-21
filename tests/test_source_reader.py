from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_core.text.source_reader import count_source_text_chars, read_source_text


class SourceReaderTests(unittest.TestCase):
    def test_count_srt_chars_ignores_index_and_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.srt"
            path.write_text(
                "1\n"
                "00:00:00,000 --> 00:00:01,500\n"
                "Hello <i>world</i>.\n\n"
                "2\n"
                "00:00:02,000 --> 00:00:03,500\n"
                "2026\n"
                "Second line.\n",
                encoding="utf-8",
            )

            expected = "Hello world.\n2026\nSecond line."
            self.assertEqual(read_source_text(path), expected)
            self.assertEqual(count_source_text_chars(path), len(expected))

    def test_count_plain_text_chars_uses_stripped_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("  Một dòng thử.\nDòng hai.  \n", encoding="utf-8")

            expected = "Một dòng thử.\nDòng hai."
            self.assertEqual(read_source_text(path), expected)
            self.assertEqual(count_source_text_chars(path), len(expected))


if __name__ == "__main__":
    unittest.main()
