"""EPUB controls and a text-only chapter preview."""

import secrets

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omni_tts_shared.epub import EPUB_PAUSE_FIELDS, EpubOptions
from omni_tts_shared.errors import ConfigError
from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget
from omni_tts_ui_qt.widgets.epub_break import EpubBreakWidget
from omni_tts_ui_qt.widgets.epub_content import EpubContentWidget


class EpubOptionsWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._breaks_dirty = False
        self._saved_breaks = {}
        form = QFormLayout(self)
        self.form = form
        hint = QLabel(
            "Chỉ áp dụng cho EPUB. Mỗi vị trí dùng một loại nghỉ. Nghỉ đoạn văn dùng mục Nhịp nghỉ; audio và SRT theo thời lượng thực."
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
        self.content = EpubContentWidget()
        self.content.changed.connect(self.changed.emit)
        form.addRow(self.content)
        self.breaks = {}
        self.pauses = {}
        for kind, title, pause_key in (
            ("title", "Sau tên chương, trước nội dung", "title_pause_ms"),
            ("chapter", "Giữa hai chương", "chapter_pause_ms"),
        ):
            editor = EpubBreakWidget(title)
            self.breaks[kind] = editor
            self.pauses[pause_key] = editor.seconds
            form.addRow(editor)
            editor.changed.connect(self._break_changed)
            editor.preview_requested.connect(
                lambda kind=kind: self._preview_break(kind)
            )
        for key, label, default in EPUB_PAUSE_FIELDS:
            if key in ("title_pause_ms", "chapter_pause_ms"):
                continue
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
        self.titles.toggled.connect(self._sync_controls)
        self.volumes.toggled.connect(self._sync_controls)
        self.output.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.music = ChapterMusicWidget(source_only=True)
        self.music.changed.connect(self.changed.emit)
        form.addRow(self.music)
        self.set_options({})

    def _break_changed(self):
        if self._updating:
            return
        self._breaks_dirty = True
        self._sync_controls()

    def _sync_controls(self, *_):
        self.breaks["title"].setEnabled(self.titles.isChecked())
        self.pauses["volume_pause_ms"].setEnabled(self.volumes.isChecked())
        self.form.labelForField(self.pauses["volume_pause_ms"]).setEnabled(
            self.volumes.isChecked()
        )
        musical = any(
            editor.options().mode == "music" and editor.options().trigger_ms > 0
            for kind, editor in self.breaks.items()
            if kind != "title" or self.titles.isChecked()
        )
        self.music.setEnabled(musical)
        if not self._updating:
            self.changed.emit()

    def _preview_break(self, kind):
        from omni_tts_core.chapter_music import (
            ChapterMusicSelector,
            preview_chapter_music,
        )
        from omni_tts_core.media_player import MediaPlayerService

        try:
            options = EpubOptions.model_validate(self.options())
            music = options.music_for(kind)
            if not music.enabled:
                return
            selected = ChapterMusicSelector(music, context=secrets.token_hex(8)).choose(
                "preview"
            )
            path = preview_chapter_music(
                selected.track_id,
                duration_ms=options.break_for(kind).trigger_ms,
                volume_percent=music.volume_percent,
                duration_mode=music.duration_mode,
                fade_in_ms=music.fade_in_ms,
                fade_out_ms=music.fade_out_ms,
            )
            MediaPlayerService().play_first_available([path])
        except (ConfigError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Chưa nghe được nhịp nghỉ", str(exc))

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
        pauses = {k: round(v.value() * 1000) for k, v in self.pauses.items()}
        if not self._breaks_dirty:
            for kind, key in (
                ("title", "title_pause_ms"),
                ("chapter", "chapter_pause_ms"),
            ):
                if kind in self._saved_breaks:
                    pauses[key] = self._saved_legacy_pauses[key]
        return EpubOptions(
            chapter_start=self.start.value(),
            chapter_end=self.end.value(),
            read_titles=self.titles.isChecked(),
            include_volumes=self.volumes.isChecked(),
            output_mode=self.output.currentData(),
            music=self.music.options(),
            content=self.content.options(),
            breaks=(
                {kind: editor.options() for kind, editor in self.breaks.items()}
                if self._breaks_dirty
                else self._saved_breaks
            ),
            **pauses,
        ).model_dump()

    def set_options(self, data):
        options = EpubOptions.model_validate(data or {})
        blocked = self.blockSignals(True)
        self._updating = True
        self._saved_breaks = dict(options.breaks)
        self._saved_legacy_pauses = {
            key: getattr(options, key) for key in ("title_pause_ms", "chapter_pause_ms")
        }
        self._breaks_dirty = False
        self.start.setValue(options.chapter_start)
        self.end.setValue(options.chapter_end)
        self.titles.setChecked(options.read_titles)
        self.volumes.setChecked(options.include_volumes)
        self.output.setCurrentIndex(self.output.findData(options.output_mode))
        self.music.set_options(options.music.model_dump())
        self.content.set_options(options.content.model_dump())
        for key, spin in self.pauses.items():
            if key not in ("title_pause_ms", "chapter_pause_ms"):
                spin.setValue(getattr(options, key) / 1000)
        for kind, editor in self.breaks.items():
            editor.set_options(options.break_for(kind))
        self._sync_controls()
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
        self.original_preview = QPlainTextEdit()
        self.original_preview.setReadOnly(True)
        self.changes_preview = QPlainTextEdit()
        self.changes_preview.setReadOnly(True)
        self.han_preview = QPlainTextEdit()
        self.han_preview.setReadOnly(True)
        tabs = QTabWidget()
        tabs.addTab(self.preview, "Văn bản sẽ đọc")
        tabs.addTab(self.original_preview, "Bản gốc")
        tabs.addTab(self.changes_preview, "Đã bỏ / đã đổi")
        tabs.addTab(self.han_preview, "Chữ Hán còn lại")
        left_layout.addWidget(self.chapters)
        left_layout.addWidget(tabs, 1)
        self.content_status = QLabel()
        self.content_status.setWordWrap(True)
        left_layout.addWidget(self.content_status)
        export_button = QPushButton("Xuất bản đọc và nguồn để kiểm tra…")
        export_button.clicked.connect(self._export_reading)
        left_layout.addWidget(export_button)
        self.chapters.currentRowChanged.connect(self._preview)
        splitter.addWidget(left)
        self.editor = EpubOptionsWidget()
        self.editor.set_options(options)
        self._reading_plan = None
        self._content_timer = QTimer(self)
        self._content_timer.setSingleShot(True)
        self._content_timer.setInterval(250)
        self._content_timer.timeout.connect(self._refresh_reading)
        self.editor.changed.connect(lambda: self._content_timer.start())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([650, 650])
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

    def _refresh_reading(self):
        from omni_tts_core.text.epub_content import (
            format_han_issues,
            prepare_epub,
            reading_summary,
        )

        try:
            self._reading_plan = prepare_epub(
                self.book, EpubOptions.model_validate(self.editor.options())
            )
            self.content_status.setText(
                reading_summary(self._reading_plan.summary)
                + "\n"
                + "\n".join(self._reading_plan.warnings)
            )
            self.han_preview.setPlainText(format_han_issues(self._reading_plan))
        except (ValueError, ConfigError) as exc:
            self._reading_plan = None
            self.content_status.setText(str(exc))
        self._preview(self.chapters.currentRow())

    def _preview(self, row):
        if row < 0:
            return
        if self._reading_plan is None:
            if self.content_status.text():
                self.preview.clear()
                return
            self._refresh_reading()
            return
        chapter = self.book.chapters[row]
        data = self._reading_plan.chapter_preview(chapter.index, max_chars=500000)
        self.preview.setPlainText(
            data["reading_text"]
            if data["included"]
            else "Phần này không nằm trong bản đọc theo phạm vi / bộ lọc hiện tại."
        )
        self.original_preview.setPlainText(data["original_text"])
        from omni_tts_core.text.epub_content import format_reading_changes

        self.changes_preview.setPlainText(format_reading_changes(data))

    def _export_reading(self):
        from pathlib import Path

        from omni_tts_core.text.epub_content import export_reading_plan
        from omni_tts_core.text.output_naming import slug_component

        self._refresh_reading()
        if self._reading_plan is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu bản đọc và nguồn"
        )
        if not directory:
            return
        try:
            paths = export_reading_plan(
                self._reading_plan,
                Path(directory),
                slug_component(self.book.title)[:100] or "epub",
            )
        except OSError as exc:
            QMessageBox.warning(self, "Chưa xuất được", str(exc))
            return
        QMessageBox.information(
            self, "Đã xuất bản đọc", "\n".join(str(p) for p in paths.values())
        )

    def _accept_options(self):
        try:
            from omni_tts_core.text.epub_content import prepare_epub

            plan = prepare_epub(
                self.book, EpubOptions.model_validate(self.editor.options())
            )
            if not plan.chapters:
                raise ConfigError(
                    "Không còn nội dung để đọc. Hãy đổi phạm vi hoặc tùy chọn lọc."
                )
        except (ValueError, ConfigError) as exc:
            QMessageBox.warning(self, "Khoảng chương chưa hợp lệ", str(exc))
            return
        self.accept()
