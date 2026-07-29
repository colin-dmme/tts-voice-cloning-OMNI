from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from omni_tts_core.authoring.capabilities import AuthoringPolicy


class AuthoringAssistBar(QWidget):
    """Generic AI-authoring entry point driven entirely by a core policy."""

    director_requested = Signal()
    configure_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("AI đạo diễn")
        self.title.setStyleSheet("font-weight: 600;")
        self.description = QLabel(
            "Phân tích nội dung và profile giọng để tạo nhiều phương án thể hiện."
        )
        self.description.setObjectName("hint")
        self.generate_button = QPushButton("✨ AI tạo script")
        self.generate_button.setObjectName("primaryButton")
        self.configure_button = QPushButton("Cấu hình AI")
        layout.addWidget(self.title)
        layout.addWidget(self.description, 1)
        layout.addWidget(self.configure_button)
        layout.addWidget(self.generate_button)
        self.generate_button.clicked.connect(self.director_requested)
        self.configure_button.clicked.connect(self.configure_requested)

    def apply_policy(self, policy: AuthoringPolicy) -> None:
        self.setVisible(policy.supported)
        self.generate_button.setEnabled(policy.enabled)
        self.generate_button.setToolTip(policy.tooltip)
        self.configure_button.setToolTip(
            "Mở trang AI / API để quản lý Gemini, model và API key."
        )
        if policy.supported:
            self.description.setText(
                f"{policy.provider_label} · {policy.dialect_id} · "
                "AI phân tích nội dung và giọng đang chọn"
            )
