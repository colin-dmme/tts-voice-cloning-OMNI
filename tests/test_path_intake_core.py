from __future__ import annotations

import unittest
from pathlib import Path

from omni_tts_core.path_intake import parse_path_text, path_from_text


class PathIntakeCoreTest(unittest.TestCase):
    def test_plain_lines(self) -> None:
        paths = parse_path_text("C:/a.txt\nC:/b.txt")
        self.assertEqual(paths, [Path("C:/a.txt"), Path("C:/b.txt")])

    def test_quoted_tokens(self) -> None:
        paths = parse_path_text('"C:/with space/a.txt" "C:/b.txt"')
        self.assertEqual(paths, [Path("C:/with space/a.txt"), Path("C:/b.txt")])

    def test_semicolon_separated(self) -> None:
        paths = parse_path_text("C:/a.txt;C:/b.txt")
        self.assertEqual(paths, [Path("C:/a.txt"), Path("C:/b.txt")])

    def test_file_url_windows_drive(self) -> None:
        self.assertEqual(path_from_text("file:///C:/x/y.txt"), Path("C:/x/y.txt"))

    def test_empty(self) -> None:
        self.assertEqual(parse_path_text(""), [])


if __name__ == "__main__":
    unittest.main()
