"""Contact page: support links (Telegram / Facebook)."""

from __future__ import annotations

import webbrowser

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_ui_qt.context import AppContext


class ContactPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        info = getattr(context.controller.service, "settings", None)
        contact = getattr(info, "contact_info", {}) if info else {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel(contact.get("title", "Liên hệ"))
        title.setObjectName("pageTitle")
        subtitle = QLabel(contact.get("subtitle", ""))
        subtitle.setObjectName("hint")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        for label, key in (("Telegram", "telegram"), ("Facebook", "facebook")):
            value = str(contact.get(key, "")).strip()
            if not value:
                continue
            layout.addLayout(self._link_row(label, value))
        layout.addStretch()

    def _link_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(f"{label}:"))
        value_label = QLabel(value)
        value_label.setTextInteractionFlags(value_label.textInteractionFlags())
        row.addWidget(value_label, 1)
        open_button = QPushButton("Mở")
        copy_button = QPushButton("Copy")
        open_button.clicked.connect(lambda: webbrowser.open(_url(value)))
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(value))
        row.addWidget(open_button)
        row.addWidget(copy_button)
        return row


def _url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"
