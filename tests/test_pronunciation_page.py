from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from omni_tts_core.pronunciation import (
    PronunciationPresetStore,
    analyze_pronunciation,
    freeze_pronunciation_selection,
)
from omni_tts_ui_qt.pages.pronunciation_page import PronunciationPage


class _PronunciationController:
    def __init__(self, root: Path) -> None:
        self.store = PronunciationPresetStore(root)

    def pronunciation_presets(self):
        return self.store.list_presets()

    def pronunciation_preset(self, preset_id: str):
        return self.store.get(preset_id)

    def save_pronunciation_preset(self, **values):
        return self.store.save(**values)

    def preview_pronunciation(self, text, selection):
        snapshot = freeze_pronunciation_selection(self.store, selection)
        return analyze_pronunciation(text, snapshot)


class PronunciationPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_page_saves_and_previews_without_putting_logic_in_widget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            controller = _PronunciationController(Path(temp_dir))
            context = SimpleNamespace(controller=controller, log=logs.append)
            page = PronunciationPage(context)
            page._clear_editor()
            page.name_edit.setText("Tên sản phẩm")
            page.rules_table.item(0, 1).setText("IIKO")
            page.rules_table.item(0, 2).setText("Y Cô")

            page._save()
            page.preview_input.setPlainText("Phân gà IIKO loại 10 lít")
            page._preview()

            self.assertEqual(len(controller.pronunciation_presets()), 1)
            self.assertIn("Y Cô", page.preview_speech.toPlainText())
            self.assertIn("IIKO → Y Cô", page.preview_summary.text())
            self.assertTrue(logs)
            page.close()


if __name__ == "__main__":
    unittest.main()