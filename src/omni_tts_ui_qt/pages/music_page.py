"""Music library, checkable mixed selections and reusable preset management."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.chapter_music import ChapterMusicLibrary, preview_chapter_music
from omni_tts_core.media_player import MediaPlayerService
from omni_tts_core.music_presets import MusicPresetStore
from omni_tts_shared.errors import ConfigError, OmniTtsError
from omni_tts_ui_qt.widgets.music_selection import MusicSelectionEditor


class MusicPage(QWidget):
    def __init__(self, context, parent=None, *, library=None):
        super().__init__(parent)
        self.context = context
        self.library = library or ChapterMusicLibrary()
        self.store = MusicPresetStore(self.library)
        self._preset_id = None
        self._loading = False
        self._dirty = False
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Quản lý nhạc, phối nhiều chủ đề và lưu preset. Chỉ các bài được tích mới tham gia random; loại nghỉ và fade vẫn chỉnh ở Studio."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter()
        left = QWidget()
        side = QVBoxLayout(left)
        side.addWidget(QLabel("PRESET NHẠC"))
        self.preset_search = QLineEdit()
        self.preset_search.setPlaceholderText("Tìm preset…")
        side.addWidget(self.preset_search)
        self.preset_list = QListWidget()
        side.addWidget(self.preset_list, 1)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Tên preset")
        side.addWidget(self.name_edit)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Mô tả khi nào nên dùng…")
        self.description_edit.setMaximumHeight(100)
        side.addWidget(self.description_edit)
        for row in [
            [("Tạo mới", self._new), ("Lưu preset", self._save)],
            [("Lưu bản sao", self._copy), ("Xóa preset", self._delete)],
        ]:
            buttons = QHBoxLayout()
            for title, callback in row:
                button = QPushButton(title)
                button.clicked.connect(callback)
                buttons.addWidget(button)
            side.addLayout(buttons)
        self.apply_preset_button = QPushButton("Dùng preset đã lưu trong Studio")
        self.apply_preset_button.clicked.connect(self._apply_preset)
        side.addWidget(self.apply_preset_button)
        use_selection = QPushButton("Dùng tập đang tích trong Studio")
        use_selection.clicked.connect(self._apply_selection)
        side.addWidget(use_selection)
        left.setMinimumWidth(250)
        split.addWidget(left)
        right = QWidget()
        main = QVBoxLayout(right)
        self.selection_editor = MusicSelectionEditor(library=self.library)
        main.addWidget(self.selection_editor, 1)
        actions = QHBoxLayout()
        for title, callback in [
            ("Nghe bản đang chọn", self._preview),
            ("Sửa mô tả / tag…", self._edit_track),
            ("Thêm nhạc…", self._import),
            ("Làm mới", self._refresh),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        main.addLayout(actions)
        self.track_description = QLabel("Chọn một dòng để xem mô tả và nghe thử.")
        self.track_description.setWordWrap(True)
        main.addWidget(self.track_description)
        split.addWidget(right)
        split.setStretchFactor(1, 4)
        layout.addWidget(split, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.selection_editor.changed.connect(self._mark_dirty)
        self.selection_editor.track_selected.connect(self._show_track)
        self.preset_list.currentItemChanged.connect(self._preset_selected)
        self.preset_search.textChanged.connect(self._filter_presets)
        self.name_edit.textChanged.connect(self._mark_dirty)
        self.description_edit.textChanged.connect(self._mark_dirty)
        self._refresh_presets()
        self._update_buttons()

    def _events(self):
        return getattr(self.context, "music_events", None)

    def _notify(self):
        events = self._events()
        if events:
            events.library_changed.emit()

    def _log(self, text):
        self.status.setText(text)
        logger = getattr(self.context, "log", None)
        if callable(logger):
            logger(text)

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self._dirty = True
        self._update_buttons()

    def _update_buttons(self):
        self.apply_preset_button.setEnabled(bool(self._preset_id) and not self._dirty)
        self.apply_preset_button.setToolTip(
            "Lưu các thay đổi trước khi dùng preset."
            if self._dirty
            else "Chọn preset làm nguồn nhạc trong Studio."
        )

    def _refresh_presets(self):
        self._loading = True
        self.preset_list.clear()
        try:
            for preset in self.store.list_presets():
                try:
                    count = f"{len(self.library.selection_tracks(preset))} bản"
                except ConfigError:
                    count = "cần kiểm tra"
                item = QListWidgetItem(f"{preset.name} · {count}")
                item.setData(Qt.ItemDataRole.UserRole, preset.preset_id)
                item.setToolTip(preset.description)
                self.preset_list.addItem(item)
                if preset.preset_id == self._preset_id:
                    self.preset_list.setCurrentItem(item)
        except ConfigError as exc:
            self.status.setText(str(exc))
        self._loading = False
        self._filter_presets()

    def _filter_presets(self, *_):
        query = self.preset_search.text().strip().casefold()
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            item.setHidden(query not in item.text().casefold())

    def _preset_selected(self, item, _previous):
        if self._loading or item is None:
            return
        try:
            preset = self.store.get(item.data(Qt.ItemDataRole.UserRole))
        except ConfigError as exc:
            self._log(str(exc))
            return
        self._loading = True
        self._preset_id = preset.preset_id
        self.name_edit.setText(preset.name)
        self.description_edit.setPlainText(preset.description)
        self.selection_editor.set_selection(preset)
        self._loading = False
        self._dirty = False
        self._update_buttons()

    def _new(self):
        self._loading = True
        self._preset_id = None
        self.preset_list.setCurrentRow(-1)
        self.name_edit.clear()
        self.description_edit.clear()
        self.selection_editor.clear_selection()
        self._loading = False
        self._dirty = False
        self._update_buttons()

    def _save(self):
        try:
            preset = self.store.save(
                self.name_edit.text(),
                preset_id=self._preset_id,
                description=self.description_edit.toPlainText(),
                **self.selection_editor.selection().model_dump(),
            )
        except (ConfigError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Chưa lưu được preset", str(exc))
            return
        self._preset_id = preset.preset_id
        self._loading = True
        self.name_edit.setText(preset.name)
        self._loading = False
        self._dirty = False
        self._refresh_presets()
        self._update_buttons()
        self._notify()
        self._log(f"Đã lưu preset nhạc: {preset.name}.")

    def _copy(self):
        self._preset_id = None
        self.name_edit.setText(self.name_edit.text().strip() + " — bản sao")
        self._save()

    def _delete(self):
        if not self._preset_id:
            return
        if (
            QMessageBox.question(
                self,
                "Xóa preset",
                "Chỉ xóa preset đã lưu; các file nhạc được giữ nguyên. Tiếp tục?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.store.delete(self._preset_id)
        except (ConfigError, OSError) as exc:
            QMessageBox.warning(self, "Chưa xóa được preset", str(exc))
            return
        self._new()
        self._refresh_presets()
        self._notify()

    def _apply_preset(self):
        if not self._preset_id or self._dirty:
            return
        events = self._events()
        if events:
            events.preset_applied.emit(self._preset_id)
        self.context.show_page("studio")
        self._log(
            "Đã chọn preset trong Studio. Đặt Loại nghỉ = Nhạc tại vị trí cần phát."
        )

    def _apply_selection(self):
        try:
            self.library.selection_tracks(self.selection_editor.selection())
        except ConfigError as exc:
            QMessageBox.warning(self, "Chưa có tập nhạc hợp lệ", str(exc))
            return
        events = self._events()
        if events:
            events.selection_applied.emit(
                self.selection_editor.selection().model_dump()
            )
        self.context.show_page("studio")
        self._log("Đã dùng tập đang tích làm nguồn random trong Studio.")

    def _show_track(self, track_id):
        try:
            track, _ = self.library.resolve(track_id)
        except ConfigError as exc:
            self.track_description.setText(str(exc))
            return
        self.track_description.setText(
            f"{track.name} — {track.description or 'Chưa có mô tả.'}"
        )

    def _preview(self):
        track_id = self.selection_editor.current_track_id()
        if not track_id:
            self.status.setText("Chọn một dòng bản nhạc để nghe.")
            return
        try:
            path = preview_chapter_music(
                track_id, duration_mode="full_track", library=self.library
            )
            MediaPlayerService().play_first_available([path])
        except (OmniTtsError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Chưa nghe được nhạc", str(exc))

    def _edit_track(self):
        track_id = self.selection_editor.current_track_id()
        if not track_id:
            self.status.setText("Chọn một dòng bản nhạc để sửa mô tả.")
            return
        track, _ = self.library.resolve(track_id)
        dialog = QDialog(self)
        dialog.setWindowTitle("Mô tả bản nhạc")
        form = QFormLayout(dialog)
        name = QLineEdit(track.name)
        description = QPlainTextEdit(track.description)
        themes = QLineEdit(", ".join(track.themes))
        tags = QLineEdit(", ".join(track.tags))
        form.addRow("Tên bản nhạc", name)
        form.addRow("Mô tả / tình huống dùng", description)
        form.addRow("Chủ đề — ID không dấu, cách bằng dấu phẩy", themes)
        form.addRow("Tag — cách bằng dấu phẩy", tags)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)

        def save():
            try:
                self.library.update_metadata(
                    track_id,
                    name=name.text(),
                    description=description.toPlainText(),
                    themes=[x.strip() for x in themes.text().split(",") if x.strip()],
                    tags=[x.strip() for x in tags.text().split(",") if x.strip()],
                )
            except (ConfigError, ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "Metadata chưa hợp lệ", str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            self._refresh()
            self._notify()

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Thêm nhạc — lấy tối đa 30 giây",
            "",
            "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)",
        )
        if not filename:
            return
        try:
            self.library.import_track(
                Path(filename),
                Path(filename).stem,
                provenance={"provider": "user_import"},
            )
        except (OmniTtsError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Chưa nhập được nhạc", str(exc))
            return
        self._refresh()
        self._notify()
        self._log("Đã nhập nhạc. Chọn dòng mới và Sửa mô tả / tag để phân nhóm.")

    def _refresh(self):
        self.selection_editor.refresh_library()
        self._refresh_presets()
