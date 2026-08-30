from __future__ import annotations

import unittest

from omni_tts_core.text.output_naming import (
    compose_stem,
    default_stem_from_text,
    format_duration_stem,
    slug_component,
)


class DefaultStemFromTextTest(unittest.TestCase):
    def test_takes_first_20_characters(self) -> None:
        text = "Bà con đã chuyển qua phân sinh học dạng dịch"
        stem = default_stem_from_text(text)
        # First 20 chars of the collapsed text, folded to a safe slug.
        self.assertEqual(stem, "Bà_con_đã_chuyển_qua")
        self.assertLessEqual(len(stem.replace("_", " ")), 20)

    def test_punctuation_and_whitespace_become_underscores(self) -> None:
        stem = default_stem_from_text("Xin chào, thế giới! Đây là...")
        self.assertNotIn(",", stem)
        self.assertNotIn("!", stem)
        self.assertNotIn(" ", stem)
        self.assertFalse(stem.startswith("_"))
        self.assertFalse(stem.endswith("_"))

    def test_collapses_runs_of_whitespace(self) -> None:
        self.assertEqual(default_stem_from_text("a\n\n  b\tc"), "a_b_c")

    def test_no_filesystem_reserved_characters(self) -> None:
        stem = default_stem_from_text('a/b\\c:d*e?"f<g>h|i')
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, stem)

    def test_empty_or_symbol_only_returns_empty(self) -> None:
        self.assertEqual(default_stem_from_text(""), "")
        self.assertEqual(default_stem_from_text("   "), "")
        self.assertEqual(default_stem_from_text("!!! ??? ..."), "")

    def test_custom_limit(self) -> None:
        self.assertEqual(default_stem_from_text("abcdefghij", limit=5), "abcde")


class FormatDurationStemTest(unittest.TestCase):
    def test_seconds_only_still_shows_minutes(self) -> None:
        self.assertEqual(format_duration_stem(45), "00m45s")

    def test_minutes_and_seconds(self) -> None:
        self.assertEqual(format_duration_stem(83), "01m23s")

    def test_hours(self) -> None:
        self.assertEqual(format_duration_stem(3700), "1h01m40s")

    def test_no_colon_ever(self) -> None:
        self.assertNotIn(":", format_duration_stem(3700))

    def test_none_and_negative(self) -> None:
        self.assertEqual(format_duration_stem(None), "00m00s")
        self.assertEqual(format_duration_stem(-5), "00m00s")


class ComposeStemTest(unittest.TestCase):
    def test_voice_and_duration_appended(self) -> None:
        self.assertEqual(
            compose_stem("Mừng_Quốc_Khánh", voice_label="ads-phan-ga-mc-nu-kagri", duration_seconds=45),
            "Mừng_Quốc_Khánh_ads_phan_ga_mc_nu_kagri_00m45s",
        )

    def test_missing_voice_skips_that_part(self) -> None:
        self.assertEqual(
            compose_stem("story", voice_label="", duration_seconds=83),
            "story_01m23s",
        )

    def test_no_suffix_args_returns_base(self) -> None:
        self.assertEqual(compose_stem("story"), "story")

    def test_slug_component_folds_special_chars(self) -> None:
        self.assertEqual(slug_component("Cô Tấm 2.0!"), "Cô_Tấm_2_0")


if __name__ == "__main__":
    unittest.main()
