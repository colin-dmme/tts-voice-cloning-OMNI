from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from omni_tts_core.pronunciation import (
    PronunciationPresetStore,
    analyze_pronunciation,
    freeze_pronunciation_selection,
)
from omni_tts_shared.pronunciation import PronunciationRule, PronunciationSelection


class PronunciationTest(unittest.TestCase):
    def test_store_round_trip_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = PronunciationPresetStore(Path(temp))
            saved = store.save(
                name="Dự án phân gà",
                project="Quảng cáo",
                rules=[PronunciationRule(written="IIKO", spoken="Y Cô")],
            )

            reloaded = PronunciationPresetStore(Path(temp)).get(saved.preset_id)
            self.assertEqual(reloaded.name, "Dự án phân gà")
            self.assertEqual(reloaded.rules[0].spoken, "Y Cô")
            self.assertEqual(reloaded.revision, 1)

            updated = store.save(
                preset_id=saved.preset_id,
                name=saved.name,
                project=saved.project,
                rules=[PronunciationRule(written="IIKO", spoken="I Cô")],
            )
            self.assertEqual(updated.revision, 2)

    def test_whole_term_keeps_display_text_and_rewrites_speech_text(self) -> None:
        snapshot = self._snapshot(
            [PronunciationRule(written="IIKO", spoken="Y Cô")]
        )
        source = "IIKO tốt hơn AIIKO, iiko vẫn là IIKO."

        analysis = analyze_pronunciation(source, snapshot)

        self.assertEqual(analysis.original_text, source)
        self.assertEqual(
            analysis.speech_text,
            "Y Cô tốt hơn AIIKO, Y Cô vẫn là Y Cô.",
        )
        self.assertEqual(analysis.match_count, 3)
        self.assertEqual(analysis.term_count, 1)
        self.assertEqual(
            [(match.start, match.end) for match in analysis.matches],
            [(0, 4), (20, 24), (32, 36)],
        )

    def test_literal_mode_and_longest_match_win(self) -> None:
        snapshot = self._snapshot(
            [
                PronunciationRule(written="AI", spoken="ây ai", match_mode="literal"),
                PronunciationRule(written="AIKO", spoken="ai cô", match_mode="literal"),
            ]
        )

        analysis = analyze_pronunciation("XAIKO", snapshot)

        self.assertEqual(analysis.speech_text, "Xai cô")
        self.assertEqual(analysis.match_count, 1)
        self.assertEqual(analysis.conflict_count, 1)

    def test_control_tags_are_protected(self) -> None:
        snapshot = self._snapshot(
            [PronunciationRule(written="speaker", spoken="người đọc", match_mode="literal")]
        )

        analysis = analyze_pronunciation(
            "<|speaker:admin|> speaker <custom speaker>", snapshot
        )

        self.assertEqual(
            analysis.speech_text,
            "<|speaker:admin|> người đọc <custom speaker>",
        )
        self.assertEqual(analysis.match_count, 1)

    def test_frozen_snapshot_does_not_change_after_preset_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = PronunciationPresetStore(Path(temp))
            preset = store.save(
                name="Tên riêng",
                rules=[PronunciationRule(written="IIKO", spoken="Y Cô")],
            )
            selection = PronunciationSelection(
                enabled=True,
                preset_ids=[preset.preset_id],
            )
            frozen = freeze_pronunciation_selection(store, selection)

            store.save(
                preset_id=preset.preset_id,
                name=preset.name,
                rules=[PronunciationRule(written="IIKO", spoken="I Cô")],
            )

            self.assertEqual(
                analyze_pronunciation("IIKO", frozen).speech_text,
                "Y Cô",
            )
            self.assertNotEqual(
                frozen.content_hash,
                freeze_pronunciation_selection(store, selection).content_hash,
            )

    @staticmethod
    def _snapshot(rules: list[PronunciationRule]):
        with tempfile.TemporaryDirectory() as temp:
            store = PronunciationPresetStore(Path(temp))
            preset = store.save(name="Kiểm thử", rules=rules)
            return freeze_pronunciation_selection(
                store,
                PronunciationSelection(enabled=True, preset_ids=[preset.preset_id]),
            )


if __name__ == "__main__":
    unittest.main()