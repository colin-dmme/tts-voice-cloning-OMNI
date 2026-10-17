"""Small standalone control panel; closing it does NOT stop the broker."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from omni_tts_ui_qt.theme import apply_theme
from omni_tts_ui_qt.widgets.broker_control import BrokerControlWidget


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Colin TTS — Quản lý chạy nền")
    apply_theme(app)
    window = QWidget()
    window.setWindowTitle("Colin TTS — Trạng thái và điều khiển broker nền")
    window.resize(650, 330)
    layout = QVBoxLayout(window)
    title = QLabel("Broker Colab trên máy này")
    title.setObjectName("pageTitle")
    layout.addWidget(title)
    control = BrokerControlWidget()
    layout.addWidget(control)
    layout.addStretch()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
