"""Optional music cues for EPUB pause slots."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from omni_tts_core.chapter_music import ChapterMusicLibrary, preview_chapter_music
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_shared.epub import ChapterMusicOptions
from omni_tts_shared.errors import ConfigError, OmniTtsError


class ChapterMusicWidget(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None, *, preview_duration=None):
        super().__init__("Nhạc đệm trong khoảng nghỉ", parent)
        self.library = ChapterMusicLibrary()
        self.preview_duration = preview_duration or (lambda: 2500)
        self._fades = (120, 350)
        self._loading = True
        self._saved_track_id = None
        self._tracks = []
        form = QFormLayout(self)
        self.enabled = QCheckBox("Bật nhạc chuyển chương")
        self.track = QComboBox()
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setSuffix(" %")
        self.between = QCheckBox("Phát giữa hai chương")
        self.after_title = QCheckBox("Phát sau tên chương, trước nội dung")
        form.addRow(self.enabled)
        form.addRow("Bản nhạc", self.track)
        form.addRow("Âm lượng nhạc", self.volume)
        form.addRow(self.between)
        form.addRow(self.after_title)
        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Nghe thử nhạc")
        self.import_button = QPushButton("Thêm nhạc…")
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.import_button)
        form.addRow(buttons)
        self.note = QLabel()
        self.note.setWordWrap(True)
        form.addRow(self.note)
        self.preview_button.clicked.connect(self._preview)
        self.import_button.clicked.connect(self._import)
        for widget in (self.enabled, self.between, self.after_title):
            widget.toggled.connect(lambda *_: self.changed.emit())
        self.track.currentIndexChanged.connect(self._track_changed)
        self.volume.valueChanged.connect(lambda *_: self.changed.emit())
        self.refresh()
        self.set_options({})
        self._loading = False

    def refresh(self, selected=None):
        loading = self._loading
        self._loading = True
        selected = selected or self.track.currentData()
        try:
            self._tracks = self.library.list_tracks()
        except ConfigError:
            self._tracks = []
        self.track.clear()
        for track in self._tracks:
            self.track.addItem(track.name, track.track_id)
        if not self._tracks:
            self.track.addItem("Thư viện chưa có nhạc — chọn Thêm nhạc…", None)
        index = self.track.findData(selected)
        if index >= 0:
            self.track.setCurrentIndex(index)
        self._track_changed()
        self._loading = loading

    def _track_changed(self, *_):
        if not self._loading:
            self._saved_track_id = self.track.currentData()
        track = next(
            (t for t in self._tracks if t.track_id == self.track.currentData()), None
        )
        note = "Tự cắt và fade cho vừa nhịp nghỉ; thời lượng audio và SRT giữ nguyên."
        if track and track.provenance.get("generated_plan") == "free":
            note += " Mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
        self.note.setText(note)
        self.changed.emit()

    def options(self):
        track_id = (
            self.track.currentData()
            if self.enabled.isChecked() or self._saved_track_id
            else None
        )
        return ChapterMusicOptions(
            enabled=self.enabled.isChecked(),
            track_id=track_id,
            volume_percent=self.volume.value(),
            between_chapters=self.between.isChecked(),
            after_title=self.after_title.isChecked(),
            fade_in_ms=self._fades[0],
            fade_out_ms=self._fades[1],
        ).model_dump()

    def set_options(self, data):
        options = ChapterMusicOptions.model_validate(data or {})
        blocked = self.blockSignals(True)
        loading = self._loading
        self._loading = True
        self._saved_track_id = options.track_id
        if options.track_id and self.track.findData(options.track_id) < 0:
            self.track.addItem("Nhạc đã lưu không còn — hãy chọn lại", options.track_id)
        if options.track_id:
            self.track.setCurrentIndex(self.track.findData(options.track_id))
        self.enabled.setChecked(options.enabled)
        self.volume.setValue(options.volume_percent)
        self.between.setChecked(options.between_chapters)
        self.after_title.setChecked(options.after_title)
        self._fades = (options.fade_in_ms, options.fade_out_ms)
        self._track_changed()
        self.blockSignals(blocked)
        self._loading = loading

    def _preview(self):
        try:
            path = preview_chapter_music(
                self.track.currentData(),
                duration_ms=self.preview_duration(),
                volume_percent=self.volume.value(),
                fade_in_ms=self._fades[0],
                fade_out_ms=self._fades[1],
            )
            MediaPlayerService().play_first_available([path])
        except (OmniTtsError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Chưa nghe được nhạc", str(exc))

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Thêm nhạc chuyển chương (lấy tối đa 30 giây)",
            "",
            "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)",
        )
        if not filename:
            return
        try:
            item = self.library.import_track(
                Path(filename),
                Path(filename).stem,
                provenance={"provider": "user_import"},
            )
            self.refresh(item.track_id)
            self._saved_track_id = item.track_id
            self.changed.emit()
        except (ConfigError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Không thêm được nhạc", str(exc))
