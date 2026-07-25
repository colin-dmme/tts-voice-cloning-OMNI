"""Entry point for Colin TTS Studio (PySide6)."""

from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from omni_tts_core.app_controller import AppController
from omni_tts_core.hardware_monitor import HardwareProbe
from omni_tts_core.safety_coordinator import SafetyGate
from omni_tts_ui_qt.main_window import MainWindow
from omni_tts_ui_qt.pages.contact_page import ContactPage
from omni_tts_ui_qt.pages.license_page import LicensePage
from omni_tts_ui_qt.pages.models_page import ModelsPage
from omni_tts_ui_qt.pages.studio_page import StudioPage
from omni_tts_ui_qt.pages.voices_page import VoicesPage
from omni_tts_ui_qt.preferences import QtPreferences
from omni_tts_ui_qt.theme import apply_theme


def _page_factories():
    return [
        ("studio", "Studio", "🎙", StudioPage),
        ("models", "Model", "📦", ModelsPage),
        ("voices", "Giọng", "🗣", VoicesPage),
        ("license", "Bản quyền", "🔑", LicensePage),
        ("contact", "Liên hệ", "✉", ContactPage),
    ]


def main() -> None:
    try:
        from omni_tts_core.user_state import restore_user_state

        restore_user_state()
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Colin TTS Studio")
    apply_theme(app)

    def excepthook(exc_type, exc_value, exc_tb) -> None:
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        QMessageBox.critical(None, "Lỗi không mong muốn", str(exc_value) or message[-1500:])
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    probe = HardwareProbe()
    service_holder = AppController()
    safety_gate = SafetyGate(service_holder.service, probe)
    service_holder.safety_gate = safety_gate

    preferences = QtPreferences()
    window = MainWindow(
        controller=service_holder,
        probe=probe,
        safety_gate=safety_gate,
        preferences=preferences,
        page_factories=[
            (key, title, icon, factory) for key, title, icon, factory in _page_factories()
        ],
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
