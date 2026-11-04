"""Optional music cues for EPUB pause slots."""

import secrets
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from omni_tts_core.chapter_music import (
    ChapterMusicLibrary,
    ChapterMusicSelector,
    music_duration_note,
    preview_chapter_music,
)
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_core.music_presets import MusicPresetStore
from omni_tts_shared.epub import ChapterMusicOptions, MusicPoolSelection
from omni_tts_shared.errors import ConfigError, OmniTtsError
from omni_tts_ui_qt.widgets.epub_break import EPUB_DISABLED_STYLE


class ChapterMusicWidget(QGroupBox):
    changed = Signal()

    def __init__(self, parent=None, *, preview_duration=None, source_only=False):
        super().__init__(
            "Nguồn nhạc cho các nhịp nghỉ"
            if source_only
            else "Nhạc đệm trong khoảng nghỉ",
            parent,
        )
        self.source_only = source_only
        if source_only:
            self.setStyleSheet(EPUB_DISABLED_STYLE)
        self.library = ChapterMusicLibrary()
        self.preview_duration = preview_duration or (lambda: 2500)
        self._fades = (120, 350)
        self._loading = True
        self._saved_track_id = None
        self._tracks = []
        self._overrides = {}
        self._pool = MusicPoolSelection()
        form = QFormLayout(self)
        self._form = form
        self.enabled = QCheckBox("Bật nhạc chuyển chương")
        self.track = QComboBox()
        self.mode = QComboBox()
        self.mode.addItem("Chọn một bản cố định", "fixed")
        self.mode.addItem("Random trong nhóm chủ đề", "random_theme")
        self.mode.addItem("Random trong tập đã tích chọn", "random_selection")
        self.mode.addItem("Random theo preset đã lưu", "preset")
        self.preset = QComboBox()
        self.pool_button = QPushButton("Tích chọn nhiều nhóm / bản nhạc…")
        self.pool_summary = QLabel("Chưa chọn tập nhạc.")
        self.pool_summary.setWordWrap(True)
        self.manage_button = QPushButton("Quản lý nhạc / preset…")
        self.manage_button.hide()
        self.theme = QComboBox()
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.shuffle_button = QPushButton("Đổi lượt trộn")
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setSuffix(" %")
        self.duration_mode = QComboBox()
        self.duration_mode.addItem("Cắt vừa khoảng nghỉ", "fit_pause")
        self.duration_mode.addItem("Phát trọn bản nhạc trong thư viện", "full_track")
        self.between = QCheckBox("Phát giữa hai chương")
        self.after_title = QCheckBox("Phát sau tên chương, trước nội dung")
        form.addRow(self.enabled)
        form.addRow("Cách chọn nhạc", self.mode)
        form.addRow("Nhóm chủ đề", self.theme)
        form.addRow("Preset nhạc", self.preset)
        form.addRow("Tập nhạc đã tích", self.pool_button)
        form.addRow(self.pool_summary)
        form.addRow("Bản nhạc", self.track)
        shuffle = QHBoxLayout()
        shuffle.addWidget(self.seed)
        shuffle.addWidget(self.shuffle_button)
        form.addRow("Lượt trộn", shuffle)
        form.addRow("Âm lượng nhạc", self.volume)
        form.addRow("Độ dài nhạc", self.duration_mode)
        form.addRow(self.between)
        form.addRow(self.after_title)
        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Nghe thử nhạc")
        self.import_button = QPushButton("Thêm nhạc…")
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.import_button)
        form.addRow(buttons)
        form.addRow(self.manage_button)
        self.note = QLabel()
        self.note.setWordWrap(True)
        form.addRow(self.note)
        if source_only:
            for control in (
                self.enabled,
                self.duration_mode,
                self.between,
                self.after_title,
                self.preview_button,
            ):
                control.hide()
                label = form.labelForField(control)
                if label:
                    label.hide()
        self.preview_button.clicked.connect(self._preview)
        self.import_button.clicked.connect(self._import)
        for widget in (self.enabled, self.between, self.after_title):
            widget.toggled.connect(lambda *_: self.changed.emit())
        self.track.currentIndexChanged.connect(self._track_changed)
        self.volume.valueChanged.connect(lambda *_: self.changed.emit())
        self.seed.valueChanged.connect(lambda *_: self.changed.emit())
        self.shuffle_button.clicked.connect(
            lambda: self.seed.setValue(secrets.randbelow(2147483647))
        )
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.theme.currentIndexChanged.connect(self._track_changed)
        self.duration_mode.currentIndexChanged.connect(self._track_changed)
        self.preset.currentIndexChanged.connect(self._track_changed)
        self.pool_button.clicked.connect(self._edit_selection)
        self.refresh()
        self.set_options({})
        self._loading = False

    def refresh(self, selected=None):
        loading = self._loading
        self._loading = True
        selected = selected or self.track.currentData()
        theme = self.theme.currentData()
        preset_id = self.preset.currentData()
        self.preset.clear()
        self.preset.addItem("Chọn preset nhạc…", None)
        try:
            for preset in MusicPresetStore(self.library).list_presets():
                self.preset.addItem(preset.name, preset.preset_id)
        except ConfigError:
            self.preset.addItem("Không đọc được preset — mở Quản lý nhạc", None)
        if preset_id and self.preset.findData(preset_id) < 0:
            self.preset.addItem("Preset đã lưu không còn", preset_id)
        self.preset.setCurrentIndex(max(0, self.preset.findData(preset_id)))
        try:
            self._tracks = self.library.list_tracks()
        except ConfigError:
            self._tracks = []
        self.track.clear()
        self.theme.clear()
        self.theme.addItem("Chọn nhóm chủ đề…", None)
        for group in self.library.list_themes():
            self.theme.addItem(
                f"{group['name']} ({group['count']} bản)", group["theme"]
            )
        if theme:
            index = self.theme.findData(theme)
            if index < 0:
                self.theme.addItem(f"Nhóm đã lưu chưa có nhạc: {theme}", theme)
                index = self.theme.count() - 1
            self.theme.setCurrentIndex(index)
        for track in self._tracks:
            self.track.addItem(track.name, track.track_id)
        if not self._tracks:
            self.track.addItem("Thư viện chưa có nhạc — chọn Thêm nhạc…", None)
        index = self.track.findData(selected)
        if index >= 0:
            self.track.setCurrentIndex(index)
        self._track_changed()
        self._loading = loading

    def _mode_changed(self, *_):
        mode = self.mode.currentData()
        random_mode = mode != "fixed"
        self.track.setEnabled(mode == "fixed")
        self.theme.setEnabled(mode == "random_theme")
        self.preset.setEnabled(mode == "preset")
        self.pool_button.setEnabled(mode == "random_selection")
        self.pool_summary.setEnabled(mode == "random_selection")
        self.seed.setEnabled(random_mode)
        self.shuffle_button.setEnabled(random_mode)
        if self.source_only:
            for control, visible in (
                (self.track, mode == "fixed"),
                (self.theme, mode == "random_theme"),
                (self.preset, mode == "preset"),
                (self.pool_button, mode == "random_selection"),
                (self.pool_summary, mode == "random_selection"),
            ):
                control.setVisible(visible)
                label = self._form.labelForField(control)
                if label:
                    label.setVisible(visible)
        self._track_changed()

    def _track_changed(self, *_):
        if not self._loading and self.mode.currentData() == "fixed":
            self._saved_track_id = self.track.currentData()
        track = next(
            (t for t in self._tracks if t.track_id == self.track.currentData()), None
        )
        note = (
            "Chọn bài hoặc nhóm nhạc dùng chung. Loại nghỉ, thời lượng và fade chỉnh riêng ở từng vị trí."
            if self.source_only
            else music_duration_note(self.duration_mode.currentData())
        )
        if self.mode.currentData() == "random_theme":
            pool = (
                self.library.list_tracks(theme=self.theme.currentData())
                if self.theme.currentData()
                else []
            )
            note += f" Random trong nhóm: {len(pool)} bản. Trộn hết nhóm trước khi lặp; cùng lượt trộn giữ kết quả khi tiếp tục tác vụ."
            if any(t.provenance.get("generated_plan") == "free" for t in pool):
                note += (
                    " Có mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
                )
        elif self.mode.currentData() in ("random_selection", "preset"):
            try:
                pool = ChapterMusicSelector(
                    ChapterMusicOptions.model_validate(self.options()), self.library
                ).pool
                note += f" Random trong {len(pool)} bản đã chọn; trộn hết tập trước khi lặp."
                if any(t.provenance.get("generated_plan") == "free" for t in pool):
                    note += " Có mẫu ElevenLabs Free: dùng cá nhân."
                self.pool_summary.setText(
                    f"{len(pool)} bản trong tập chọn."
                    if self.mode.currentData() == "random_selection"
                    else "Tập chọn được quản lý trong tab Nhạc."
                )
            except ConfigError as exc:
                note += " " + str(exc)
                self.pool_summary.setText(str(exc))
        elif track:
            note += f"\n{track.description or 'Chưa có mô tả.'}\nChủ đề: {', '.join(track.themes)}. Tag: {', '.join(track.tags)}."
        if (
            self.mode.currentData() == "fixed"
            and track
            and track.provenance.get("generated_plan") == "free"
        ):
            note += " Mẫu ElevenLabs Free: dùng cá nhân; chưa có quyền thương mại."
        self.note.setText(note)
        self.changed.emit()

    def options(self):
        track_id = (
            self.track.currentData()
            if self.enabled.isChecked()
            or self._saved_track_id
            or (self.source_only and self.isEnabled())
            else None
        )
        if self.mode.currentData() != "fixed":
            track_id = self._saved_track_id
        return ChapterMusicOptions(
            enabled=self.enabled.isChecked(),
            track_id=track_id,
            selection_mode=self.mode.currentData(),
            preset_id=self.preset.currentData(),
            **self._pool.model_dump(),
            duration_mode=self.duration_mode.currentData(),
            theme=self.theme.currentData(),
            random_seed=self.seed.value(),
            track_overrides=self._overrides,
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
        self._overrides = dict(options.track_overrides)
        self._pool = MusicPoolSelection(
            **{key: getattr(options, key) for key in MusicPoolSelection.model_fields}
        )
        if options.preset_id and self.preset.findData(options.preset_id) < 0:
            self.preset.addItem("Preset đã lưu không còn", options.preset_id)
        self.preset.setCurrentIndex(max(0, self.preset.findData(options.preset_id)))
        self.mode.setCurrentIndex(self.mode.findData(options.selection_mode))
        self.duration_mode.setCurrentIndex(
            self.duration_mode.findData(options.duration_mode)
        )
        if options.theme and self.theme.findData(options.theme) < 0:
            self.theme.addItem(
                f"Nhóm đã lưu chưa có nhạc: {options.theme}", options.theme
            )
        self.theme.setCurrentIndex(max(0, self.theme.findData(options.theme)))
        self.seed.setValue(options.random_seed)
        if options.track_id and self.track.findData(options.track_id) < 0:
            self.track.addItem("Nhạc đã lưu không còn — hãy chọn lại", options.track_id)
        if options.track_id:
            self.track.setCurrentIndex(self.track.findData(options.track_id))
        self.enabled.setChecked(options.enabled)
        self.volume.setValue(options.volume_percent)
        self.between.setChecked(options.between_chapters)
        self.after_title.setChecked(options.after_title)
        self._fades = (options.fade_in_ms, options.fade_out_ms)
        self._mode_changed()
        self.blockSignals(blocked)
        self._loading = loading

    def apply_preset(self, preset_id):
        self.refresh()
        self.set_options(
            {**self.options(), "selection_mode": "preset", "preset_id": preset_id}
        )
        self.changed.emit()

    def apply_selection(self, selection):
        pool = MusicPoolSelection.model_validate(selection)
        self.set_options(
            {
                **self.options(),
                **pool.model_dump(),
                "selection_mode": "random_selection",
            }
        )
        self.changed.emit()

    def _edit_selection(self):
        from omni_tts_ui_qt.widgets.music_selection import MusicSelectionEditor

        dialog = QDialog(self)
        dialog.setWindowTitle("Tích chọn nhạc để random")
        dialog.resize(1050, 650)
        layout = QVBoxLayout(dialog)
        editor = MusicSelectionEditor(library=self.library)
        initial = self._pool
        if not initial.theme_ids and not initial.track_ids and self.theme.currentData():
            initial = MusicPoolSelection(theme_ids=[self.theme.currentData()])
        editor.set_selection(initial)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        def accept():
            try:
                self.library.selection_tracks(editor.selection())
            except ConfigError as exc:
                QMessageBox.warning(dialog, "Chưa có tập nhạc hợp lệ", str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            self.apply_selection(editor.selection().model_dump())

    def _preview(self):
        try:
            options = ChapterMusicOptions.model_validate(self.options())
            # Preview another sample without changing the persisted generation seed/plan.
            selected = ChapterMusicSelector(
                options, self.library, context=secrets.token_hex(8)
            ).choose("preview")
            path = preview_chapter_music(
                selected.track_id,
                duration_ms=self.preview_duration(),
                volume_percent=self.volume.value(),
                fade_in_ms=self._fades[0],
                fade_out_ms=self._fades[1],
                duration_mode=options.duration_mode,
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
            self.mode.setCurrentIndex(self.mode.findData("fixed"))
            self.changed.emit()
        except (ConfigError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Không thêm được nhạc", str(exc))
