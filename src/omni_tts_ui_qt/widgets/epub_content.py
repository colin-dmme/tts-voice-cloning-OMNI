"""Compact EPUB content policy editor shared by Studio and import preview."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from omni_tts_shared.epub import EpubContentOptions


class EpubContentWidget(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Nội dung đưa vào giọng đọc", parent)
        self._readings = {}
        form = QFormLayout(self)
        self.skip_references = QCheckBox("Bỏ nguồn / tài liệu tham khảo khỏi lời đọc")
        self.read_notes = QCheckBox("Giữ ghi chú giải thích trong nội dung")
        self.url_mode = QComboBox()
        for label, value in [
            ("Không đọc URL / DOI", "skip"),
            ("Chỉ đọc tên miền", "domain"),
            ("Đọc nguyên địa chỉ", "read"),
        ]:
            self.url_mode.addItem(label, value)
        self.url_mode.setToolTip(
            "Nhãn link có nghĩa vẫn được giữ, ví dụ ‘xem mục 18’. Không mở các liên kết."
        )
        self.han_mode = QComboBox()
        for label, value in [
            ("Dùng nghĩa Việt sẵn có; báo chữ Hán còn lại", "prefer_vietnamese"),
            ("Giữ chữ Hán và cảnh báo", "warn"),
            ("Giữ chữ Hán, không cảnh báo", "keep"),
        ]:
            self.han_mode.addItem(label, value)
        self.include_frontmatter = QCheckBox("Đọc phần giới thiệu / thuật ngữ")
        self.include_appendices = QCheckBox("Đọc phụ lục nội dung")
        self.include_technical_notes = QCheckBox("Đọc ghi chú kỹ thuật cuối sách")
        self.export_references = QCheckBox("Xuất nguồn tham khảo riêng cạnh audio")
        form.addRow(self.skip_references)
        form.addRow(self.read_notes)
        form.addRow("Đường link", self.url_mode)
        form.addRow("Chữ Hán", self.han_mode)
        self.readings_button = QPushButton()
        self.readings_button.clicked.connect(self._edit_readings)
        form.addRow(self.readings_button)
        for widget in (
            self.include_frontmatter,
            self.include_appendices,
            self.include_technical_notes,
            self.export_references,
        ):
            form.addRow(widget)
        hint = QLabel(
            "Xem bản gốc / bản đọc / phần đã bỏ khi Nhập EPUB. Văn bản đọc và báo cáo lọc được lưu cùng audio; không sửa sách gốc."
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        for widget in self.findChildren(QCheckBox):
            widget.toggled.connect(lambda *_: self.changed.emit())
        for widget in (self.url_mode, self.han_mode):
            widget.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.set_options({})

    def options(self):
        values = {
            name: getattr(self, name).isChecked()
            for name in (
                "skip_references",
                "read_notes",
                "include_frontmatter",
                "include_appendices",
                "include_technical_notes",
                "export_references",
            )
        }
        return EpubContentOptions(
            **values,
            url_mode=self.url_mode.currentData(),
            han_mode=self.han_mode.currentData(),
            han_readings=self._readings,
        ).model_dump()

    def set_options(self, value):
        options = EpubContentOptions.model_validate(value or {})
        blocked = self.blockSignals(True)
        for name in (
            "skip_references",
            "read_notes",
            "include_frontmatter",
            "include_appendices",
            "include_technical_notes",
            "export_references",
        ):
            getattr(self, name).setChecked(getattr(options, name))
        self.url_mode.setCurrentIndex(self.url_mode.findData(options.url_mode))
        self.han_mode.setCurrentIndex(self.han_mode.findData(options.han_mode))
        self._readings = dict(options.han_readings)
        self.readings_button.setText(f"Cách đọc chữ Hán… ({len(self._readings)} cụm)")
        self.blockSignals(blocked)

    def _edit_readings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Cách đọc chữ Hán trong sách")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Mỗi dòng: chữ gốc = cách đọc. Các cách đọc này áp dụng trước chế độ chữ Hán."
            )
        )
        editor = QPlainTextEdit(
            "\n".join(f"{a} = {b}" for a, b in self._readings.items())
        )
        editor.setPlaceholderText("万 = vạn\n医保 = bảo hiểm y tế")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        def save():
            try:
                from omni_tts_core.text.epub_content import parse_han_readings

                readings = parse_han_readings(editor.toPlainText())
            except ValueError as exc:
                QMessageBox.warning(dialog, "Cách đọc chưa hợp lệ", str(exc))
                return
            self._readings = readings
            self.readings_button.setText(f"Cách đọc chữ Hán… ({len(readings)} cụm)")
            self.changed.emit()
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.resize(570, 330)
        dialog.exec()
