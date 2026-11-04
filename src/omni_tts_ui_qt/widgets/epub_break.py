"""A single EPUB boundary, with controls that follow the selected pause type."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
)

from omni_tts_shared.epub import EpubBreakOptions

EPUB_DISABLED_STYLE = """
QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {
    color: #626277;
    background-color: #0b0b13;
    border-color: #20202d;
}
QLabel:disabled, QGroupBox:disabled { color: #626277; }
"""


class EpubBreakWidget(QGroupBox):
    changed = Signal()
    preview_requested = Signal()

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(EPUB_DISABLED_STYLE)
        self._loading = False
        self.form = QFormLayout(self)
        self.kind = QComboBox()
        for text, value in (
            ("Không nghỉ", "none"),
            ("Khoảng lặng", "silence"),
            ("Nhạc", "music"),
        ):
            self.kind.addItem(text, value)
        self.duration_mode = QComboBox()
        self.duration_mode.addItem("Số giây cố định", "fit_pause")
        self.duration_mode.addItem("Phát trọn bản nhạc", "full_track")
        self.seconds = self._seconds(10, 0.1)
        self.fade_in = self._seconds(2, 0.05)
        self.fade_out = self._seconds(3, 0.05)
        self.form.addRow("Loại nghỉ", self.kind)
        self.form.addRow("Độ dài nhạc", self.duration_mode)
        self.form.addRow("Số giây cố định", self.seconds)
        self.form.addRow("Fade-in — nhạc vào dần", self.fade_in)
        self.form.addRow("Fade-out — nhạc tắt dần", self.fade_out)
        self.preview = QPushButton("Nghe thử nhịp này")
        self.form.addRow(self.preview)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.form.addRow(self.note)
        self.kind.currentIndexChanged.connect(self._sync)
        self.duration_mode.currentIndexChanged.connect(self._sync)
        for spin in (self.seconds, self.fade_in, self.fade_out):
            spin.valueChanged.connect(self._sync)
        self.preview.clicked.connect(self.preview_requested.emit)
        self.set_options(EpubBreakOptions())

    @staticmethod
    def _seconds(maximum, step):
        spin = QDoubleSpinBox()
        spin.setRange(0, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(step)
        spin.setSuffix(" giây")
        return spin

    def _activate(self, control, enabled):
        control.setEnabled(enabled)
        label = self.form.labelForField(control)
        if label:
            label.setEnabled(enabled)

    def _sync(self, *_):
        mode = self.kind.currentData()
        musical = mode == "music"
        full = musical and self.duration_mode.currentData() == "full_track"
        audible = musical and (full or self.seconds.value() > 0)
        self._activate(self.duration_mode, musical)
        self._activate(self.seconds, mode != "none" and not full)
        self._activate(self.fade_in, audible)
        self._activate(self.fade_out, audible)
        self.preview.setEnabled(audible)
        if mode == "none":
            note = "Đọc liền sang phần tiếp theo; không chèn khoảng lặng hoặc nhạc."
        elif full:
            note = "Theo độ dài từng bản nhạc. Ô số giây không áp dụng; không cộng thêm khoảng lặng. SRT tự cập nhật."
        elif musical:
            note = "Nhạc chiếm đúng số giây trên; tự cắt/đệm và fade. Fade dài sẽ co theo nhịp ngắn."
        else:
            note = (
                "Khoảng lặng đúng số giây trên; không phát nhạc. 0 giây = không nghỉ."
            )
        self.note.setText(note)
        if not self._loading:
            self.changed.emit()

    def options(self):
        return EpubBreakOptions(
            mode=self.kind.currentData(),
            duration_mode=self.duration_mode.currentData(),
            duration_ms=round(self.seconds.value() * 1000),
            fade_in_ms=round(self.fade_in.value() * 1000),
            fade_out_ms=round(self.fade_out.value() * 1000),
        )

    def set_options(self, options):
        options = EpubBreakOptions.model_validate(options)
        self._loading = True
        self.kind.setCurrentIndex(self.kind.findData(options.mode))
        self.duration_mode.setCurrentIndex(
            self.duration_mode.findData(options.duration_mode)
        )
        self.seconds.setValue(options.duration_ms / 1000)
        self.fade_in.setValue(options.fade_in_ms / 1000)
        self.fade_out.setValue(options.fade_out_ms / 1000)
        self._sync()
        self._loading = False
