"""EPUB controls and a text-only chapter preview."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from omni_tts_shared.epub import EPUB_PAUSE_FIELDS, EpubOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget


class EpubOptionsWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        form = QFormLayout(self)
        hint = QLabel(
            "Chỉ áp dụng cho EPUB. Nghỉ đoạn văn dùng mục Nhịp nghỉ. Audio và SRT cùng tính các khoảng lặng."
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        self.start, self.end = QSpinBox(), QSpinBox()
        self.start.setRange(1, 100000)
        self.end.setRange(0, 100000)
        self.end.setSpecialValueText("Hết sách")
        self.end.setToolTip(
            "Chọn theo vị trí chương trong danh sách xem trước. 0 = hết sách."
        )
        form.addRow("Từ chương (vị trí)", self.start)
        form.addRow("Đến chương", self.end)
        self.titles = QCheckBox("Đọc tên chương trước nội dung")
        self.volumes = QCheckBox("Đọc tên quyển khi bắt đầu quyển")
        form.addRow(self.titles)
        form.addRow(self.volumes)
        self.output = QComboBox()
        self.output.addItem("Mỗi chương một audio", "chapters")
        self.output.addItem("Ghép thành một audio", "merged")
        self.output.setToolTip(
            "SRT chỉ được xuất khi bật Xuất kèm SRT ở Đầu ra. EPUB dùng lựa chọn này thay cho Tách theo đoạn."
        )
        form.addRow("Cách xuất EPUB", self.output)
        self.pauses = {}
        for key, label, default in EPUB_PAUSE_FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(0, 10)
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setSuffix(" giây")
            spin.setValue(default / 1000)
            spin.setToolTip(
                "Khoảng lặng chèn thêm. 0 = không chèn. Không cộng chồng với nghỉ đoạn ở cùng ranh giới."
            )
            self.pauses[key] = spin
            form.addRow(label, spin)
            spin.valueChanged.connect(lambda *_: self.changed.emit())
        self.start.valueChanged.connect(self._start_changed)
        self.end.valueChanged.connect(self._end_changed)
        self.titles.toggled.connect(lambda *_: self.changed.emit())
        self.volumes.toggled.connect(lambda *_: self.changed.emit())
        self.output.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.music = ChapterMusicWidget(preview_duration=lambda: round(self.pauses["chapter_pause_ms"].value() * 1000))
        self.music.changed.connect(self.changed.emit)
        form.addRow(self.music)
        self.set_options({})

    def _start_changed(self, value):
        if not self._updating:
            if self.end.value() and self.end.value() < value:
                self.end.setValue(value)
            self.changed.emit()

    def _end_changed(self, value):
        if not self._updating:
            if value and value < self.start.value():
                self.start.setValue(value)
            self.changed.emit()

    def options(self):
        return EpubOptions(
            chapter_start=self.start.value(),
            chapter_end=self.end.value(),
            read_titles=self.titles.isChecked(),
            include_volumes=self.volumes.isChecked(),
            output_mode=self.output.currentData(),
            music=self.music.options(),
            **{k: round(v.value() * 1000) for k, v in self.pauses.items()},
        ).model_dump()

    def set_options(self, data):
        options = EpubOptions.model_validate(data or {})
        blocked = self.blockSignals(True)
        self._updating = True
        self.start.setValue(options.chapter_start)
        self.end.setValue(options.chapter_end)
        self.titles.setChecked(options.read_titles)
        self.volumes.setChecked(options.include_volumes)
        self.output.setCurrentIndex(self.output.findData(options.output_mode))
        self.music.set_options(options.music.model_dump())
        for key, spin in self.pauses.items():
            spin.setValue(getattr(options, key) / 1000)
        self.blockSignals(blocked)
        self._updating = False


class EpubImportDialog(QDialog):
    def __init__(self, book, options, parent=None, *, create_srt=False):
        super().__init__(parent)
        self.book = book
        self.setWindowTitle("Nhập EPUB — xem trước nội dung đọc")
        self.resize(1000, 730)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{book.title}\n{len(book.chapters)} chương · {len(book.skipped_documents)} phần điều hướng/bìa được bỏ qua. Chưa tạo giọng."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.chapters = QListWidget()
        self.chapters.addItems([f"{c.index}. {c.title}" for c in book.chapters])
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        left_layout.addWidget(self.chapters)
        left_layout.addWidget(self.preview)
        self.chapters.currentRowChanged.connect(self._preview)
        splitter.addWidget(left)
        self.editor = EpubOptionsWidget()
        self.editor.set_options(options)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        splitter.addWidget(scroll)
        layout.addWidget(splitter, 1)
        self.create_srt = QCheckBox("Xuất kèm phụ đề .srt khớp với audio")
        self.create_srt.setChecked(create_srt)
        layout.addWidget(self.create_srt)
        if book.warnings:
            warning = QLabel("Lưu ý: " + "\n".join(book.warnings[:5]))
            warning.setWordWrap(True)
            layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Thêm vào hàng đợi")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.accepted.connect(self._accept_options)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.chapters.setCurrentRow(0)

    def _preview(self, row):
        if row >= 0:
            chapter = self.book.chapters[row]
            self.preview.setPlainText(
                chapter.title
                + "\n\n"
                + "\n\n".join(
                    "[Nghỉ chuyển cảnh]" if b.role == "scene" else b.text
                    for b in chapter.blocks
                )
            )

    def _accept_options(self):
        try:
            self.book.select(EpubOptions.model_validate(self.editor.options()))
        except (ValueError, ConfigError) as exc:
            QMessageBox.warning(self, "Khoảng chương chưa hợp lệ", str(exc))
            return
        self.accept()
