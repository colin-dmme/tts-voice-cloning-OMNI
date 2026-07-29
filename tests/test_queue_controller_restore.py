from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from omni_tts_core.file_queue import FileQueueStatus, FileQueueStore
from omni_tts_core.generation_history import GenerationHistoryStore
from omni_tts_ui_qt.pages.queue_controller import QueueController


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
            self.assertEqual(restored.last_error, "")


if __name__ == "__main__":
    unittest.main()
