from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from omni_tts_ui_qt.widgets.wheel_guard import install_parameter_wheel_guard


class ParameterWheelGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        install_parameter_wheel_guard(cls.app)

    @staticmethod
    def _wheel(target: QWidget, delta: int = -120) -> None:
        event = QWheelEvent(
            QPointF(4, 4),
            QPointF(4, 4),
            QPoint(),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(target, event)

    def test_wheel_does_not_change_spin_or_combo(self) -> None:
        spin = QSpinBox()
        spin.setRange(0, 10)
        spin.setValue(5)
        combo = QComboBox()
        combo.addItems(["Một", "Hai", "Ba"])
        combo.setCurrentIndex(1)

        self._wheel(spin)
        self._wheel(combo)

        self.assertEqual(spin.value(), 5)
        self.assertEqual(combo.currentIndex(), 1)

    def test_wheel_over_parameter_scrolls_nearest_page(self) -> None:
        area = QScrollArea()
        area.resize(240, 120)
        content = QWidget()
        content.setMinimumHeight(900)
        layout = QVBoxLayout(content)
        spin = QSpinBox()
        spin.setValue(5)
        layout.addWidget(spin)
        layout.addStretch()
        area.setWidget(content)
        area.setWidgetResizable(True)
        area.show()
        QApplication.processEvents()
        before = area.verticalScrollBar().value()

        self._wheel(spin)

        self.assertEqual(spin.value(), 5)
        self.assertGreater(area.verticalScrollBar().value(), before)
        area.close()


if __name__ == "__main__":
    unittest.main()
