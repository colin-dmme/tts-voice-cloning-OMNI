from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tkinter import Tcl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_ui_tkinter.path_intake import parse_path_text


class TestPathIntake(unittest.TestCase):
    def test_parse_lines_semicolons_tabs_and_file_urls(self) -> None:
        text = (
            "C:/Source/one.srt\n"
            "C:/Source/two.md; C:/Source/three.txt\n"
            "file:///C:/Source/four%20space.srt\tC:/Source/five.srt"
        )

        paths = parse_path_text(text, Tcl().splitlist)

        self.assertEqual(
            [path.as_posix() for path in paths],
            [
                "C:/Source/one.srt",
                "C:/Source/two.md",
                "C:/Source/three.txt",
                "C:/Source/four space.srt",
                "C:/Source/five.srt",
            ],
        )

    def test_parse_quoted_and_tcl_braced_paths(self) -> None:
        text = r'"C:\Folder One\a file.srt" {D:\Folder Two\b file.md}'

        paths = parse_path_text(text, Tcl().splitlist)

        self.assertEqual(
            [path.as_posix() for path in paths],
            ["C:/Folder One/a file.srt", "D:/Folder Two/b file.md"],
        )

    def test_unquoted_single_path_with_spaces_stays_whole(self) -> None:
        paths = parse_path_text(r"C:\Folder With Spaces\one file.srt", Tcl().splitlist)

        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].as_posix(), "C:/Folder With Spaces/one file.srt")


if __name__ == "__main__":
    unittest.main()
