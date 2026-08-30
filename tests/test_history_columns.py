from __future__ import annotations

import unittest

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_core.generation_history import GenerationHistoryEntry, HistoryStatus
from omni_tts_core.ui_presenters.history_columns import (
    history_language_label,
    history_voice_label,
)


def _entry(snapshot: dict) -> GenerationHistoryEntry:
    return GenerationHistoryEntry(
        history_id="h1",
        mode="text",
        source_label="Văn bản trực tiếp",
        source_path=None,
        char_count=10,
        model_id="omnivoice_base",
        provider_id="omnivoice",
        status=HistoryStatus.DONE,
        duration_seconds=1.0,
        output_manifest=FileQueueOutputManifest(),
        settings_snapshot=snapshot,
        source_text="",
        error="",
        created_at="2026-08-18T09:52:54",
    )


class HistoryLanguageLabelTest(unittest.TestCase):
    def test_known_language_code_is_translated(self) -> None:
        self.assertEqual(history_language_label(_entry({"language": "vi"})), "Tiếng Việt")

    def test_missing_language_returns_dash(self) -> None:
        self.assertEqual(history_language_label(_entry({})), "—")


class HistoryVoiceLabelTest(unittest.TestCase):
    def test_profile_resolves_to_name(self) -> None:
        entry = _entry({"voice_source_mode": "profile", "voice_profile_id": "p1"})
        self.assertEqual(history_voice_label(entry, {"p1": "ads-phan-ga"}), "ads-phan-ga")

    def test_profile_without_name_falls_back_to_short_id(self) -> None:
        entry = _entry({"voice_source_mode": "profile", "voice_profile_id": "abcdef123456"})
        self.assertEqual(history_voice_label(entry, {}), "Profile #abcdef12")

    def test_fixed_voice_uses_speaker_id(self) -> None:
        entry = _entry({"voice_source_mode": "fixed", "speaker_id": "nu-mien-bac"})
        self.assertEqual(history_voice_label(entry, {}), "nu-mien-bac")

    def test_fixed_voice_default(self) -> None:
        entry = _entry({"voice_source_mode": "fixed"})
        self.assertEqual(history_voice_label(entry, {}), "Giọng mặc định")

    def test_empty_snapshot_returns_dash(self) -> None:
        self.assertEqual(history_voice_label(_entry({}), {}), "—")


if __name__ == "__main__":
    unittest.main()
