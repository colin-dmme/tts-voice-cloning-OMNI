from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.higgs.authoring_catalog import (
    HiggsTagOption,
    featured_higgs_tags,
    higgs_tag_groups,
)


class HiggsScriptToolbar(QWidget):
    token_requested = Signal(str)
    validate_requested = Signal()
    preview_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Higgs Script")
        title.setToolTip(
            "Các điều khiển này là token nằm trong nội dung, không phải "
            "tham số sampling của request."
        )
        title.setStyleSheet("font-weight: 600;")
        header.addWidget(title)

        instruction = QLabel("Bấm một nút để chèn tag tại con trỏ")
        instruction.setObjectName("hint")
        header.addWidget(instruction)
        header.addStretch(1)

        self.quick_buttons: list[QToolButton] = []
        for option in featured_higgs_tags():
            button = self._tag_button(option)
            button.setProperty("higgsQuickAction", True)
            self.quick_buttons.append(button)
            header.addWidget(button)

        self.validate = QPushButton("Kiểm tra tag")
        self.preview = QPushButton("Xem request")
        self.validate.setToolTip(
            "Kiểm tra cú pháp, tag không hỗ trợ và cách đặt SFX trong nội dung."
        )
        self.preview.setToolTip(
            "Xem các request thực tế sau khi chuẩn hóa, chia đoạn và kế thừa "
            "trạng thái delivery."
        )
        header.addWidget(self.validate)
        header.addWidget(self.preview)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.tag_buttons: list[QToolButton] = []
        for group in higgs_tag_groups():
            page = QFrame()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(8, 6, 8, 8)
            page_layout.setSpacing(5)

            hint = QLabel(group.description)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            page_layout.addWidget(hint)

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(5)
            visible_options = tuple(
                option for option in group.options if not option.featured
            )
            column_count = self._column_count(len(visible_options))
            for index, option in enumerate(visible_options):
                button = self._tag_button(option)
                self.tag_buttons.append(button)
                grid.addWidget(
                    button,
                    index // column_count,
                    index % column_count,
                )
            for column in range(column_count):
                grid.setColumnStretch(column, 1)
            page_layout.addLayout(grid)
            self.tabs.addTab(page, group.label)
            self.tabs.setTabToolTip(
                self.tabs.count() - 1,
                group.description,
            )

        layout.addWidget(self.tabs)
        self.validate.clicked.connect(self.validate_requested)
        self.preview.clicked.connect(self.preview_requested)

    def _tag_button(self, option: HiggsTagOption) -> QToolButton:
        button = QToolButton(self)
        button.setText(option.label)
        button.setToolTip(option.tooltip)
        button.setProperty("higgsTagToken", option.token)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        button.clicked.connect(
            lambda _checked=False, token=option.token: self.token_requested.emit(
                token
            )
        )
        return button

    @staticmethod
    def _column_count(option_count: int) -> int:
        if option_count >= 16:
            return 4
        if option_count >= 8:
            return 4
        if option_count >= 4:
            return 4
        return max(1, option_count)
