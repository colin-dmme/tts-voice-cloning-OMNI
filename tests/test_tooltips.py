from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from omni_tts_core.ui_presenters.tooltips import TOOLTIPS, tooltip

_SRC = Path(__file__).resolve().parents[1] / "src"
_GUI_DIRS = (_SRC / "omni_tts_ui_qt", _SRC / "omni_tts_ui_tkinter")
_CALL = re.compile(r'tooltip\(\s*"([a-z0-9_]+)"\s*\)')


def _called_keys(directory: Path) -> set[str]:
    """Keys passed straight to ``tooltip("...")`` — where a typo can hide."""
    keys: set[str] = set()
    for path in directory.rglob("*.py"):
        keys.update(_CALL.findall(path.read_text(encoding="utf-8")))
    return keys


def _keys_used_by(directory: Path) -> set[str]:
    """Every catalogue key the GUI mentions, including the ones it passes through
    a table as ``tooltip_key`` rather than calling directly."""
    keys: set[str] = set()
    for path in directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in TOOLTIPS:
                keys.add(node.value)
    return keys


class CatalogueTest(unittest.TestCase):
    def test_every_key_a_gui_asks_for_exists(self) -> None:
        """A typo'd key silently shows an empty tooltip, which is exactly the
        confusion this catalogue is meant to remove."""
        for directory in _GUI_DIRS:
            for key in _called_keys(directory):
                with self.subTest(gui=directory.name, key=key):
                    self.assertIn(key, TOOLTIPS)
                    self.assertTrue(TOOLTIPS[key].strip())

    def test_both_guis_explain_the_shared_controls_identically(self) -> None:
        qt_keys = _keys_used_by(_GUI_DIRS[0])
        tk_keys = _keys_used_by(_GUI_DIRS[1])
        shared = qt_keys & tk_keys
        self.assertTrue(shared, "hai giao diện phải dùng chung ít nhất một tooltip")
        # Same key means same text by construction; assert the catalogue is the
        # only source so a future GUI cannot fork the wording.
        for key in shared:
            self.assertEqual(tooltip(key), TOOLTIPS[key])

    def test_gpu_safety_help_is_available_to_both_guis(self) -> None:
        gpu_keys = {key for key in TOOLTIPS if key.startswith("gpu_")}
        qt_keys = _keys_used_by(_GUI_DIRS[0])
        tk_keys = _keys_used_by(_GUI_DIRS[1])
        for key in gpu_keys:
            with self.subTest(key=key):
                self.assertIn(key, qt_keys)
                self.assertIn(key, tk_keys)

    def test_unknown_key_returns_empty_string(self) -> None:
        self.assertEqual(tooltip("khong_ton_tai"), "")


if __name__ == "__main__":
    unittest.main()
