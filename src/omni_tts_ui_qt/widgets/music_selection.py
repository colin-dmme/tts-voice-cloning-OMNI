"""Checkable theme/track editor shared by the music manager and Studio dialog."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.chapter_music import ChapterMusicLibrary, music_theme_label
from omni_tts_shared.epub import MusicPoolSelection


class MusicSelectionEditor(QWidget):
    changed = Signal()
    track_selected = Signal(str)

    def __init__(self, parent=None, *, library=None):
        super().__init__(parent)
        self.library = library or ChapterMusicLibrary()
        self._themes = set()
        self._tracks = set()
        self._excluded = set()
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Tích nhiều nhóm để phối nhạc; có thể thêm/bỏ từng bài. Nhóm đã tích tự nhận bài mới; bài trùng chỉ tính một lần."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.theme_search = QLineEdit()
        self.theme_search.setPlaceholderText("Tìm nhóm chủ đề…")
        self.theme_list = QListWidget()
        left_layout.addWidget(self.theme_search)
        left_layout.addWidget(self.theme_list)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.track_search = QLineEdit()
        self.track_search.setPlaceholderText("Tìm bản nhạc, tag, nhạc cụ, mô tả…")
        self.checked_only = QCheckBox("Chỉ xem các bản đã tích")
        right_layout.addWidget(self.track_search)
        right_layout.addWidget(self.checked_only)
        self.tracks_table = QTableWidget(0, 5)
        self.tracks_table.setHorizontalHeaderLabels(
            ["Dùng", "Bản nhạc", "Chủ đề", "Giây", "Tag"]
        )
        self.tracks_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tracks_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tracks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tracks_table.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self.tracks_table, 1)
        tools = QHBoxLayout()
        for text, callback in [
            ("Tích các bản đang hiển thị", lambda: self._bulk(True)),
            ("Bỏ tích đang hiển thị", lambda: self._bulk(False)),
            ("Bỏ toàn bộ", self.clear_selection),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            tools.addWidget(button)
        right_layout.addLayout(tools)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.theme_list.itemChanged.connect(self._theme_checked)
        self.tracks_table.itemChanged.connect(self._track_checked)
        self.tracks_table.currentItemChanged.connect(self._current_track)
        self.theme_search.textChanged.connect(self._filter)
        self.track_search.textChanged.connect(self._filter)
        self.checked_only.toggled.connect(self._filter)
        self.refresh_library()

    def selection(self):
        return MusicPoolSelection(
            theme_ids=sorted(self._themes),
            track_ids=sorted(self._tracks),
            excluded_track_ids=sorted(self._excluded),
        )

    def set_selection(self, value):
        selection = (
            value
            if isinstance(value, MusicPoolSelection)
            else MusicPoolSelection.model_validate(value)
        )
        self._themes = set(selection.theme_ids)
        self._tracks = set(selection.track_ids)
        self._excluded = set(selection.excluded_track_ids)
        self.refresh_library()
        self.changed.emit()

    def clear_selection(self):
        self.set_selection(MusicPoolSelection())

    def refresh_library(self):
        self._loading = True
        self.tracks = self.library.list_tracks()
        self._by_id = {t.track_id: t for t in self.tracks}
        self.theme_list.clear()
        groups = {g["theme"]: g for g in self.library.list_themes()}
        for theme in sorted(set(groups) | self._themes):
            group = groups.get(theme, {"name": theme + " (không còn bài)", "count": 0})
            item = QListWidgetItem(f"{group['name']} ({group['count']})")
            item.setData(Qt.ItemDataRole.UserRole, theme)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            self.theme_list.addItem(item)
        self.tracks_table.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            for column, text in enumerate(
                [
                    "",
                    track.name,
                    ", ".join(music_theme_label(t) for t in track.themes),
                    f"{track.duration_seconds:.1f}",
                    ", ".join(track.tags),
                ]
            ):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, track.track_id)
                item.setToolTip(track.description or "Chưa có mô tả.")
                if column == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                self.tracks_table.setItem(row, column, item)
        self.tracks_table.setColumnWidth(0, 44)
        self.tracks_table.setColumnWidth(1, 235)
        self.tracks_table.setColumnWidth(2, 175)
        self.tracks_table.setColumnWidth(3, 55)
        self._loading = False
        self._sync_checks()

    def _selected_ids(self):
        return {
            t.track_id
            for t in self.tracks
            if (self._themes.intersection(t.themes) or t.track_id in self._tracks)
            and t.track_id not in self._excluded
        }

    def _sync_checks(self):
        self._loading = True
        selected = self._selected_ids()
        for i in range(self.theme_list.count()):
            item = self.theme_list.item(i)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.data(Qt.ItemDataRole.UserRole) in self._themes
                else Qt.CheckState.Unchecked
            )
        for row in range(self.tracks_table.rowCount()):
            item = self.tracks_table.item(row, 0)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.data(Qt.ItemDataRole.UserRole) in selected
                else Qt.CheckState.Unchecked
            )
        self._loading = False
        self._filter()

    def _theme_checked(self, item):
        if self._loading:
            return
        theme = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._themes.add(theme)
        else:
            self._themes.discard(theme)
        self._sync_checks()
        self.changed.emit()

    def _set_track(self, track_id, checked):
        track = self._by_id[track_id]
        if checked:
            self._excluded.discard(track_id)
            if not self._themes.intersection(track.themes):
                self._tracks.add(track_id)
        else:
            self._tracks.discard(track_id)
            if self._themes.intersection(track.themes):
                self._excluded.add(track_id)
            else:
                self._excluded.discard(track_id)

    def _track_checked(self, item):
        if self._loading or item.column() != 0:
            return
        self._set_track(
            item.data(Qt.ItemDataRole.UserRole),
            item.checkState() == Qt.CheckState.Checked,
        )
        self._sync_checks()
        self.changed.emit()

    def _bulk(self, checked):
        for row in range(self.tracks_table.rowCount()):
            if not self.tracks_table.isRowHidden(row):
                self._set_track(
                    self.tracks_table.item(row, 0).data(Qt.ItemDataRole.UserRole),
                    checked,
                )
        self._sync_checks()
        self.changed.emit()

    def _filter(self, *_):
        theme_query = self.theme_search.text().casefold().strip()
        for i in range(self.theme_list.count()):
            item = self.theme_list.item(i)
            item.setHidden(theme_query not in item.text().casefold())
        query = self.track_search.text().casefold().strip()
        selected = self._selected_ids()
        shown = 0
        for row, track in enumerate(self.tracks):
            match = (
                query
                in " ".join(
                    [
                        track.name,
                        track.track_id,
                        track.description,
                        *track.tags,
                        *track.themes,
                    ]
                ).casefold()
            )
            visible = match and (
                not self.checked_only.isChecked() or track.track_id in selected
            )
            self.tracks_table.setRowHidden(row, not visible)
            shown += int(visible)
        self.summary.setText(
            f"Đã tích {len(selected)} bản trong toàn thư viện · Hiển thị {shown}/{len(self.tracks)}. Tìm kiếm không làm mất lựa chọn."
        )

    def _current_track(self, item, _previous):
        if item:
            self.track_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def current_track_id(self):
        item = self.tracks_table.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None
