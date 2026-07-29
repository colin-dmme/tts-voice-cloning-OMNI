from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters.pause_explanations import build_pause_explanation


class PauseExplanationTest(unittest.TestCase):
    def test_current_random_sentence_and_paragraph_values_are_not_stacked(self) -> None:
        explanation = build_pause_explanation(
            {
                "punctuation_pause_enabled": True,
                "sentence_pause_random_enabled": True,
                "sentence_pause_min_ms": 260,
                "sentence_pause_max_ms": 280,
                "chunk_pause_ms": 120,
                "paragraph_pause_ms": 300,
            }
        )
        self.assertIn("giữa cùng một đoạn: nghỉ 0,26–0,28 giây", explanation.section)
        self.assertIn("chỉ nghỉ đoạn gốc 0,3 giây", explanation.section)
        self.assertIn("KHÔNG cộng thành 0,56–0,58 giây", explanation.section)
        self.assertIn("không cộng thêm nghỉ cuối câu", explanation.paragraph)
        self.assertIn("nghỉ 0,09 giây sau dấu phẩy", explanation.comma)

    def test_disabled_punctuation_still_explains_paragraph_and_chunk_pauses(self) -> None:
        explanation = build_pause_explanation(
            {
                "punctuation_pause_enabled": False,
                "chunk_pause_ms": 120,
                "paragraph_pause_ms": 300,
            }
        )
        self.assertIn("Ngắt nghỉ theo dấu câu đang tắt", explanation.section)
        self.assertIn("nghỉ đoạn gốc 0,3 giây", explanation.section)
        self.assertIn("Ranh giới chunk dùng 0,12 giây", explanation.section)

    def test_random_paragraph_range_is_explained_without_stacking(self) -> None:
        explanation = build_pause_explanation(
            {
                "punctuation_pause_enabled": True,
                "sentence_pause_ms": 300,
                "sentence_pause_random_enabled": False,
                "paragraph_pause_random_enabled": True,
                "paragraph_pause_min_ms": 250,
                "paragraph_pause_max_ms": 350,
            }
        )
        self.assertIn("chỉ nghỉ đoạn gốc 0,25–0,35 giây", explanation.section)
        self.assertIn("KHÔNG cộng thành 0,55–0,65 giây", explanation.section)
        self.assertIn("Mỗi ranh giới đoạn lấy độc lập", explanation.paragraph)


if __name__ == "__main__":
    unittest.main()
