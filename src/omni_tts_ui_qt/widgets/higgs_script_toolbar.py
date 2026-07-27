from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.higgs.script import (
    EMOTIONS,
    PROSODY,
    SOUND_EFFECTS,
    STYLES,
)


_GROUPS = (
    ("Emotion", "emotion", EMOTIONS),
    ("Style", "style", STYLES),
    (
        "Speed",
        "prosody",
        tuple(value for value in PROSODY if value.startswith("speed_")),
    ),
    (
        "Pitch",
        "prosody",
        tuple(value for value in PROSODY if value.startswith("pitch_")),
    ),
    (
        "Expressiveness",
        "prosody",
        tuple(value for value in PROSODY if value.startswith("expressive_")),
    ),
    ("SFX", "sfx", SOUND_EFFECTS),
)


class HiggsScriptToolbar(QWidget):
    token_requested = Signal(str)
    validate_requested = Signal()
    preview_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        title = QLabel("Higgs Script:")
        title.setToolTip(
            "Các điều khiển này là token nằm trong nội dung, không phải "
            "tham số sampling của request."
        )
        self.group = QComboBox()
        for label, category, values in _GROUPS:
            self.group.addItem(label, (category, values))
        self.value = QComboBox()
        self.insert = QPushButton("Chèn tại con trỏ")
        self.pause = QPushButton("Pause")
        self.long_pause = QPushButton("Long pause")
        self.validate = QPushButton("Kiểm tra tag")
        self.preview = QPushButton("Xem request")
        row.addWidget(title)
        row.addWidget(self.group)
        row.addWidget(self.value, 1)
        row.addWidget(self.insert)
        row.addWidget(self.pause)
        row.addWidget(self.long_pause)
        row.addWidget(self.validate)
        row.addWidget(self.preview)
        layout.addLayout(row)

        hint = QLabel(
            "Delivery tag đặt trước đoạn cần điều khiển; Pause/SFX được chèn "
            "đúng vị trí. SFX nên đi sát từ tượng thanh."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.group.currentIndexChanged.connect(self._reload_values)
        self.insert.clicked.connect(self._insert_selected)
        self.pause.clicked.connect(
            lambda: self.token_requested.emit("<|prosody:pause|>")
        )
        self.long_pause.clicked.connect(
            lambda: self.token_requested.emit("<|prosody:long_pause|>")
        )
        self.validate.clicked.connect(self.validate_requested)
        self.preview.clicked.connect(self.preview_requested)
        self._reload_values()

    def _reload_values(self, *_args) -> None:
        self.value.clear()
        data = self.group.currentData()
        if not data:
            return
        _category, values = data
        for value in values:
            self.value.addItem(value.replace("_", " "), value)

    def _insert_selected(self) -> None:
        data = self.group.currentData()
        value = self.value.currentData()
        if not data or not value:
            return
        category, _values = data
        self.token_requested.emit(f"<|{category}:{value}|>")
