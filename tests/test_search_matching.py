from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters.search import matches_search, normalize_search


class NormalizeSearchTest(unittest.TestCase):
    def test_strips_vietnamese_tone_marks(self) -> None:
        self.assertEqual(normalize_search("Ngọc Huyền"), "ngoc huyen")
        self.assertEqual(normalize_search("Miền Nam"), "mien nam")

    def test_maps_d_with_stroke(self) -> None:
        self.assertEqual(normalize_search("Đạt Phi"), "dat phi")

    def test_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_search("  PIPER  "), "piper")


class MatchesSearchTest(unittest.TestCase):
    def test_accentless_needle_finds_accented_text(self) -> None:
        self.assertTrue(matches_search("Piper Ngọc Huyền v1", "ngoc"))
        self.assertTrue(matches_search("Piper Ngọc Huyền v1", "huyen"))

    def test_accented_needle_still_works(self) -> None:
        self.assertTrue(matches_search("Piper Ngọc Huyền v1", "Ngọc"))

    def test_empty_needle_matches_everything(self) -> None:
        self.assertTrue(matches_search("bất kỳ", ""))
        self.assertTrue(matches_search("bất kỳ", "   "))

    def test_non_matching(self) -> None:
        self.assertFalse(matches_search("Piper Ban Mai", "chatterbox"))


if __name__ == "__main__":
    unittest.main()
