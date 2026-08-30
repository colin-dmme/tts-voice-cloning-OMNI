from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from omni_tts_core.file_queue import (
    FileQueuePronunciationMode,
    FileQueueStatus,
    FileQueueStore,
    queue_settings_fingerprint,
)
from omni_tts_core.generation_history import GenerationHistoryStore
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.pages.queue_controller import QueueController


class _PreviewController:
    @staticmethod
    def preview_pronunciation(_text, selection):
        snapshot_hash = (
            "preset:" + ",".join(selection.preset_ids)
            if selection.enabled
            else "disabled"
        )
        return SimpleNamespace(snapshot_hash=snapshot_hash)


class QueueControllerRestoreTest(unittest.TestCase):
    def test_historical_source_is_added_or_reset_as_pending_with_fresh_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "story.txt"
            source.write_text("Nội dung cũ", encoding="utf-8")
            store = FileQueueStore(root / "queue.sqlite3")
            controller = QueueController(
                SimpleNamespace(),
                GenerationHistoryStore(root / "history.sqlite3"),
                store=store,
            )

            first = controller.prepare_source_for_rerun(source)
            store.mark_failed(first.item_id, "old error")
            source.write_text("Nội dung mới dài hơn", encoding="utf-8")
            restored = controller.prepare_source_for_rerun(source)

            self.assertEqual(restored.item_id, first.item_id)
            self.assertEqual(restored.status, FileQueueStatus.PENDING)
            self.assertEqual(restored.char_count, len("Nội dung mới dài hơn"))
            self.assertEqual(restored.unit_count, 1)
            self.assertEqual(restored.last_error, "")

    def test_studio_preset_change_only_invalidates_inherited_queue_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inherited_source = root / "inherited.txt"
            off_source = root / "off.txt"
            inherited_output = root / "inherited.wav"
            off_output = root / "off.wav"
            for path in (inherited_source, off_source):
                path.write_text("IIKO", encoding="utf-8")
            for path in (inherited_output, off_output):
                path.write_bytes(b"wav")

            store = FileQueueStore(root / "queue.sqlite3")
            inherited, _ = store.add(inherited_source, 4)
            off, _ = store.add(off_source, 4)
            store.set_pronunciation_binding(
                [off.item_id],
                mode=FileQueuePronunciationMode.OFF,
            )
            old_settings = GenerationSettings(
                pronunciation_enabled=True,
                pronunciation_preset_ids=["old"],
            )
            payload = old_settings.to_request("x").model_dump(mode="json")
            for item, output, snapshot_hash in (
                (inherited, inherited_output, "preset:old"),
                (off, off_output, "disabled"),
            ):
                store.mark_running(item.item_id)
                store.mark_done(
                    item.item_id,
                    job_id=f"job-{item.item_id}",
                    output_paths=[output],
                    fingerprint=queue_settings_fingerprint(payload, snapshot_hash),
                )

            controller = QueueController(
                SimpleNamespace(controller=_PreviewController()),
                GenerationHistoryStore(root / "history.sqlite3"),
                store=store,
            )
            controller.mark_settings_outdated(
                GenerationSettings(
                    pronunciation_enabled=True,
                    pronunciation_preset_ids=["new"],
                )
            )

            self.assertEqual(
                store.get(inherited.item_id).status,
                FileQueueStatus.OUTDATED,
            )
            self.assertEqual(store.get(off.item_id).status, FileQueueStatus.DONE)


if __name__ == "__main__":
    unittest.main()
