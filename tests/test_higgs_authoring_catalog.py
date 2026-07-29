from __future__ import annotations

import unittest

from omni_tts_core.higgs.authoring_catalog import (
    EMOTIONS,
    PROSODY,
    SOUND_EFFECTS,
    STYLES,
    featured_higgs_tags,
    higgs_tag_groups,
)
from omni_tts_core.higgs.script import validate_higgs_script


class HiggsAuthoringCatalogTest(unittest.TestCase):
    def test_catalog_covers_every_supported_tag_once(self) -> None:
        options = [
            option
            for group in higgs_tag_groups()
            for option in group.options
        ]
        tokens = [option.token for option in options]
        expected_count = (
            len(EMOTIONS)
            + len(STYLES)
            + len(SOUND_EFFECTS)
            + len(PROSODY)
        )
        self.assertEqual(len(tokens), expected_count)
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertTrue(all(validate_higgs_script(token).valid for token in tokens))

    def test_user_facing_metadata_is_vietnamese_and_complete(self) -> None:
        groups = higgs_tag_groups()
        self.assertEqual(
            [group.label for group in groups],
            ["Cảm xúc", "Phong cách", "Nhịp & biểu cảm", "SFX giọng nói"],
        )
        for group in groups:
            self.assertTrue(group.description.strip())
            for option in group.options:
                self.assertTrue(option.label.strip())
                self.assertIn("Cách dùng:", option.tooltip)
                self.assertIn(option.token, option.tooltip)

    def test_pause_actions_are_featured_for_one_click_insertion(self) -> None:
        self.assertEqual(
            [option.value for option in featured_higgs_tags()],
            ["pause", "long_pause"],
        )
        self.assertEqual(
            [option.label for option in featured_higgs_tags()],
            ["Nghỉ ngắn", "Nghỉ dài"],
        )


if __name__ == "__main__":
    unittest.main()
