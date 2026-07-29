from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_core.generation_history import GenerationHistoryEntry, HistoryStatus
from omni_tts_core.history_restore import (
    build_history_restore_plan,
    restore_setting_mismatches,
)
from omni_tts_core.ui_presenters.history_details import format_history_settings
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import OmniTtsError


def _entry(**overrides) -> GenerationHistoryEntry:
    values = {
        "history_id": "history-1",
        "mode": "text",
        "source_label": "Văn bản trực tiếp",
        "source_path": None,
        "char_count": 12,
        "model_id": "piper_ngoc_huyen",
        "provider_id": "piper",
        "status": HistoryStatus.DONE,
        "duration_seconds": 1.2,
        "output_manifest": FileQueueOutputManifest(),
        "settings_snapshot": GenerationSettings(
            model_id="piper_ngoc_huyen", speed=1.2
        ).to_snapshot(),
        "source_text": "Xin chào lịch sử",
        "error": "",
        "created_at": "2026-07-28T10:00:00",
    }
    values.update(overrides)
    return GenerationHistoryEntry(**values)


class HistoryRestoreTest(unittest.TestCase):
    def test_text_plan_restores_source_and_full_settings(self) -> None:
        plan = build_history_restore_plan(_entry())
        self.assertEqual(plan.mode, "text")
        self.assertEqual(plan.source_text, "Xin chào lịch sử")
        self.assertEqual(plan.settings.speed, 1.2)

    def test_file_plan_requires_the_original_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "story.txt"
            source.write_text("Nội dung", encoding="utf-8")
            plan = build_history_restore_plan(
                _entry(mode="file", source_path=source, source_text="")
            )
            self.assertEqual(plan.source_path, source)

    def test_legacy_entry_without_snapshot_is_not_claimed_as_exact(self) -> None:
        with self.assertRaisesRegex(OmniTtsError, "chưa có snapshot"):
            build_history_restore_plan(_entry(settings_snapshot={}))

    def test_setting_mismatch_reports_only_fields_the_panel_must_apply(self) -> None:
        expected = GenerationSettings(speed=1.2, output_stem="old-name")
        actual = GenerationSettings(speed=1.0, output_stem="new-name")
        self.assertEqual(restore_setting_mismatches(expected, actual), ("speed",))

    def test_details_include_primary_values_and_full_snapshot(self) -> None:
        details = format_history_settings(_entry())
        self.assertIn("Model: piper_ngoc_huyen", details)
        self.assertIn("Tốc độ: 1.2", details)
        self.assertIn("TOÀN BỘ SNAPSHOT SETTING", details)
        self.assertIn('"sentence_pause_ms": 320', details)


if __name__ == "__main__":
    unittest.main()
