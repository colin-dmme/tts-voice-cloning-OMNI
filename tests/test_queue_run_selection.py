import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from omni_tts_core.file_queue import FileQueueStatus, FileQueueStore
from omni_tts_core.generation_history import GenerationHistoryStore
from omni_tts_shared.pronunciation import PronunciationSelection
from omni_tts_ui_qt.pages.queue_controller import QueueController
from omni_tts_ui_tkinter.app import TkinterApp


class QueueRunSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = FileQueueStore(root / "queue.sqlite3")
        self.controller = QueueController(
            SimpleNamespace(),
            GenerationHistoryStore(root / "history.sqlite3"),
            store=self.store,
        )
        self.ids = {}
        for name in [
            "pending.txt",
            "outdated.epub",
            "done.txt",
            "failed.txt",
            "cancelled.txt",
            "interrupted.txt",
            "running.txt",
        ]:
            source = root / name
            source.write_text("source", encoding="utf-8")
            item, _ = self.store.add(source, 6, unit_count=1)
            self.ids[name] = item.item_id

        for name in ["outdated.epub", "done.txt"]:
            output = root / (name + ".wav")
            output.write_bytes(b"completed audio")
            self.store.mark_running(self.ids[name])
            self.store.mark_done(
                self.ids[name],
                job_id=name,
                output_paths=[output],
                fingerprint="old-settings",
            )
        # The same transition as changing EPUB/music settings after a successful run.
        self.store.mark_settings_outdated_by_item(
            {self.ids["outdated.epub"]: "new-settings"}
        )
        self.store.mark_failed(self.ids["failed.txt"], "previous failure")
        self.store.mark_cancelled(self.ids["cancelled.txt"])
        self.store.mark_running(self.ids["interrupted.txt"])
        self.store.recover_and_validate()
        self.store.mark_running(self.ids["running.txt"])

    def test_qt_run_queue_includes_outdated_epub_without_rerunning_other_states(self):
        tasks = self.controller._tasks_for("pending", [], PronunciationSelection())

        self.assertEqual(
            [task.source_path.name for task in tasks], ["pending.txt", "outdated.epub"]
        )
        self.assertEqual(
            self.store.get(self.ids["done.txt"]).status, FileQueueStatus.DONE
        )

    def test_tk_run_queue_includes_outdated_epub_without_rerunning_other_states(self):
        # No GUI root or model is required to exercise the real queue selection.
        app = object.__new__(TkinterApp)
        app.source_file_items = {item.item_id: item for item in self.store.list_items()}

        items = app._source_items_for_run("pending")

        self.assertEqual(
            [item.source_path.name for item in items], ["pending.txt", "outdated.epub"]
        )

    def test_qt_run_selected_still_reruns_only_explicit_selection(self):
        selected = [self.ids["done.txt"], self.ids["running.txt"]]
        tasks = self.controller._tasks_for(
            "selected", selected, PronunciationSelection()
        )

        self.assertEqual([task.source_path.name for task in tasks], ["done.txt"])


if __name__ == "__main__":
    unittest.main()
