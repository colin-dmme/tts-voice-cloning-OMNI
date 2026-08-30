from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtCore import Qt

from omni_tts_core.file_queue import (
    FileQueueItem,
    FileQueuePronunciationMode,
    FileQueueStatus,
    path_key,
)
from omni_tts_ui_qt.models.queue_model import QueueTableModel


class QueueTableModelTest(unittest.TestCase):
    def test_shows_predicted_split_file_count_next_to_character_count(self) -> None:
        source = Path("C:/input/story.txt")
        item = FileQueueItem(
            item_id="one",
            source_path=source,
            path_key=path_key(source),
            char_count=529_023,
            unit_count=1_087,
            status=FileQueueStatus.PENDING,
        )
        model = QueueTableModel()
        model.set_items([item])

        self.assertEqual(model.columnCount(), 9)
        self.assertEqual(
            model.headerData(2, Qt.Orientation.Horizontal), "Số đoạn"
        )
        self.assertEqual(model.data(model.index(0, 1)), "529,023")
        self.assertEqual(model.data(model.index(0, 2)), "1,087")
        self.assertIn(
            "Số file audio dự kiến",
            model.data(model.index(0, 2), Qt.ItemDataRole.ToolTipRole),
        )

    def test_shows_pronunciation_binding_stats_and_details(self) -> None:
        source = Path("C:/input/story.txt")
        item = FileQueueItem(
            item_id="pronunciation",
            source_path=source,
            path_key=path_key(source),
            char_count=0,
            pronunciation_mode=FileQueuePronunciationMode.PRESET,
            pronunciation_preset_ids=["ads"],
            pronunciation_term_count=1,
            pronunciation_match_count=3,
            pronunciation_conflict_count=0,
            pronunciation_details="IIKO → Y Cô ×3",
        )
        model = QueueTableModel()
        model.set_items([item], preset_names={"ads": "Tên sản phẩm"})

        index = model.index(0, 3)
        self.assertEqual(model.headerData(3, Qt.Orientation.Horizontal), "Cách đọc")
        self.assertEqual(
            model.data(index),
            "Preset: Tên sản phẩm · 1 từ / 3 lần",
        )
        self.assertIn(
            "IIKO → Y Cô ×3",
            model.data(index, Qt.ItemDataRole.ToolTipRole),
        )


if __name__ == "__main__":
    unittest.main()
