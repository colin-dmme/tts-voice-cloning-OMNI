import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omni_tts_core.chapter_music import ChapterMusicSelector
from omni_tts_shared.epub import ChapterMusicOptions
from tests.test_music_themes import make_library


class MusicManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_checkbox_pool_and_exclusions_survive_search_filter(self):
        from omni_tts_ui_qt.widgets.music_selection import MusicSelectionEditor

        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            editor = MusicSelectionEditor(library=library)
            for i in range(editor.theme_list.count()):
                editor.theme_list.item(i).setCheckState(Qt.CheckState.Checked)
            row = next(
                r
                for r in range(editor.tracks_table.rowCount())
                if editor.tracks_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
                == "cue-1"
            )
            editor.tracks_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
            editor.track_search.setText("Music 3")
            self.assertEqual(
                [t.track_id for t in library.selection_tracks(editor.selection())],
                ["cue-0", "cue-2", "cue-3"],
            )
            self.assertIn("cue-1", editor.selection().excluded_track_ids)
            editor.track_search.clear()
            self.assertEqual(
                editor.tracks_table.item(row, 0).checkState(), Qt.CheckState.Unchecked
            )
            editor.close()

    def test_manager_saves_preset_and_applies_it_to_studio_source_control(self):
        from omni_tts_ui_qt.context import MusicEvents
        from omni_tts_ui_qt.pages.music_page import MusicPage
        from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget

        with tempfile.TemporaryDirectory() as temp:
            library = make_library(Path(temp))
            events = MusicEvents()
            logs = []
            context = SimpleNamespace(
                music_events=events, log=logs.append, show_page=lambda key: None
            )
            with patch(
                "omni_tts_core.chapter_music.default_music_root",
                return_value=library.root,
            ):
                page = MusicPage(context, library=library)
                page.selection_editor.set_selection(
                    {
                        "theme_ids": ["tam-quoc", "ngon-tinh"],
                        "excluded_track_ids": ["cue-1"],
                    }
                )
                page.name_edit.setText("Truyện trộn hai nhóm")
                page._save()
                self.assertEqual(len(page.store.list_presets()), 1)
                source = ChapterMusicWidget()
                events.preset_applied.connect(source.apply_preset)
                page._apply_preset()
                chosen = ChapterMusicOptions.model_validate(source.options())
                self.assertEqual(chosen.selection_mode, "preset")
                self.assertEqual(
                    [t.track_id for t in ChapterMusicSelector(chosen, library).pool],
                    ["cue-0", "cue-2", "cue-3"],
                )
                self.assertTrue(logs)
                source.close()
                page.close()

    def test_sidebar_has_music_page(self):
        from omni_tts_ui_qt.main import _page_factories

        self.assertIn("music", [row[0] for row in _page_factories()])


if __name__ == "__main__":
    unittest.main()
