"""Voice library: two sub-tabs — Clone profiles and Designed voices.

All search/filter/group logic lives in ``omni_tts_core.voice_library``; this page
only binds widgets to it. Clone profiles carry reference audio; designed voices
carry only a text description (``instruct``) used by Voice-Design providers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.voice_library import (
    build_voice_items,
    filter_voice_items,
    list_projects,
    list_tags,
)
from omni_tts_ui_qt.context import AppContext

_LANGUAGES = [("vi — Tiếng Việt", "vi"), ("en — English", "en"), ("zh", "zh"), ("ja", "ja"), ("ko", "ko")]
_ROLES = ["neutral", "storytelling", "news", "emotional", "fast", "slow"]
_AUDIO_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)"
_ALL = "(Tất cả)"


def _parse_tags(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _filter_bar(on_change) -> tuple[QWidget, QLineEdit, QComboBox, QComboBox]:
    """Search box + project + tag filters. Returns (widget, search, project, tag)."""
    bar = QWidget()
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    search = QLineEdit()
    search.setPlaceholderText("Tìm theo tên, dự án, tag…")
    search.setClearButtonEnabled(True)
    project = QComboBox()
    tag = QComboBox()
    row.addWidget(search, 1)
    row.addWidget(QLabel("Dự án:"))
    row.addWidget(project)
    row.addWidget(QLabel("Tag:"))
    row.addWidget(tag)
    search.textChanged.connect(lambda _t: on_change())
    project.currentIndexChanged.connect(lambda _i: on_change())
    tag.currentIndexChanged.connect(lambda _i: on_change())
    return bar, search, project, tag


class VoicesPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._editing_id: str | None = None
        self._audio_path: Path | None = None
        self._design_editing_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Thư viện giọng")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_clone_tab(), "Clone (audio mẫu)")
        tabs.addTab(self._build_design_tab(), "Thiết kế (mô tả)")
        layout.addWidget(tabs, 1)
        self.refresh()

    # === Clone tab =========================================================

    def _build_clone_tab(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        bar, self.clone_search, self.clone_project, self.clone_tag = _filter_bar(
            self._refresh_clone_list
        )
        outer.addWidget(bar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_clone_list())
        splitter.addWidget(self._build_clone_editor())
        splitter.setSizes([280, 620])
        outer.addWidget(splitter, 1)
        return panel

    def _build_clone_list(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.profile_list.itemDoubleClicked.connect(self._preview_profile_item)
        refresh = QPushButton("Làm mới")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(self.profile_list, 1)
        layout.addWidget(refresh)
        panel.setMinimumWidth(240)
        return panel

    def _build_clone_editor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        audio_row = QHBoxLayout()
        self.audio_edit = QLineEdit()
        self.audio_edit.setReadOnly(True)
        pick = QPushButton("Chọn…")
        pick.clicked.connect(self._pick_audio)
        self.audio_preview_button = QPushButton("▶ Nghe")
        self.audio_preview_button.setEnabled(False)
        self.audio_preview_button.setToolTip(
            "Mở audio mẫu bằng trình nghe nhạc mặc định của Windows."
        )
        self.audio_preview_button.clicked.connect(self._preview_main_sample)
        audio_row.addWidget(self.audio_edit, 1)
        audio_row.addWidget(self.audio_preview_button)
        audio_row.addWidget(pick)
        self.audio_meta = QLabel("")
        self.audio_meta.setObjectName("hint")
        self.project_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Cách nhau bằng dấu phẩy: nam, quảng cáo…")
        self.language_combo = QComboBox()
        for label, code in _LANGUAGES:
            self.language_combo.addItem(label, code)
        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setMaximumHeight(90)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(60)
        form.addRow("Tên:", self.name_edit)
        form.addRow("Audio mẫu:", audio_row)
        form.addRow("", self.audio_meta)
        form.addRow("Dự án:", self.project_edit)
        form.addRow("Tag:", self.tags_edit)
        form.addRow("Ngôn ngữ:", self.language_combo)
        form.addRow("Transcript:", self.transcript_edit)
        form.addRow("Ghi chú:", self.notes_edit)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        save = QPushButton("Lưu profile")
        save.setObjectName("primaryButton")
        new = QPushButton("Tạo mới")
        delete = QPushButton("Xóa profile")
        save.clicked.connect(self._save)
        new.clicked.connect(self._clear_editor)
        delete.clicked.connect(self._delete)
        for button in (save, new, delete):
            button_row.addWidget(button)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addWidget(QLabel("Mẫu phụ (tối đa 2, tổng 3 mẫu):"))
        self.samples_table = QTableWidget(0, 4)
        self.samples_table.setHorizontalHeaderLabels(["Mặc định", "Vai trò", "Thời lượng", "Transcript"])
        self.samples_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.samples_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.samples_table.setMaximumHeight(140)
        self.samples_table.doubleClicked.connect(self._preview_selected_sample)
        layout.addWidget(self.samples_table)
        sample_row = QHBoxLayout()
        self.role_combo = QComboBox()
        self.role_combo.addItems(_ROLES)
        preview_sample = QPushButton("▶ Nghe mẫu chọn")
        preview_sample.clicked.connect(self._preview_selected_sample)
        add_sample = QPushButton("Thêm mẫu phụ")
        remove_sample = QPushButton("Xóa mẫu chọn")
        default_sample = QPushButton("Đặt làm mặc định")
        add_sample.clicked.connect(self._add_sample)
        remove_sample.clicked.connect(self._remove_sample)
        default_sample.clicked.connect(self._set_default_sample)
        sample_row.addWidget(QLabel("Vai trò:"))
        sample_row.addWidget(self.role_combo)
        sample_row.addWidget(preview_sample)
        sample_row.addWidget(add_sample)
        sample_row.addWidget(remove_sample)
        sample_row.addWidget(default_sample)
        sample_row.addStretch()
        layout.addLayout(sample_row)
        return panel

    # === Design tab ========================================================

    def _build_design_tab(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        bar, self.design_search, self.design_project, self.design_tag = _filter_bar(
            self._refresh_design_list
        )
        outer.addWidget(bar)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.design_list = QListWidget()
        self.design_list.currentItemChanged.connect(self._on_design_selected)
        refresh = QPushButton("Làm mới")
        refresh.clicked.connect(self.refresh)
        left_layout.addWidget(self.design_list, 1)
        left_layout.addWidget(refresh)
        left.setMinimumWidth(240)
        splitter.addWidget(left)

        editor = QWidget()
        elayout = QVBoxLayout(editor)
        form = QFormLayout()
        self.design_name = QLineEdit()
        self.design_instruct = QPlainTextEdit()
        self.design_instruct.setPlaceholderText(
            "Mô tả thuộc tính giọng, tiếng Anh ổn định nhất. "
            "Vd: female, low pitch, warm, news anchor"
        )
        self.design_instruct.setMaximumHeight(90)
        self.design_project_edit = QLineEdit()
        self.design_tags_edit = QLineEdit()
        self.design_tags_edit.setPlaceholderText("Cách nhau bằng dấu phẩy: nữ, tin tức…")
        self.design_language = QComboBox()
        for label, code in _LANGUAGES:
            self.design_language.addItem(label, code)
        self.design_notes = QPlainTextEdit()
        self.design_notes.setMaximumHeight(60)
        form.addRow("Tên:", self.design_name)
        form.addRow("Mô tả (instruct):", self.design_instruct)
        form.addRow("Dự án:", self.design_project_edit)
        form.addRow("Tag:", self.design_tags_edit)
        form.addRow("Ngôn ngữ:", self.design_language)
        form.addRow("Ghi chú:", self.design_notes)
        elayout.addLayout(form)
        hint = QLabel(
            "Giọng thiết kế chỉ dùng được với model hỗ trợ Voice Design (OmniVoice)."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        elayout.addWidget(hint)
        button_row = QHBoxLayout()
        save = QPushButton("Lưu giọng thiết kế")
        save.setObjectName("primaryButton")
        new = QPushButton("Tạo mới")
        delete = QPushButton("Xóa")
        save.clicked.connect(self._save_design)
        new.clicked.connect(self._clear_design_editor)
        delete.clicked.connect(self._delete_design)
        for button in (save, new, delete):
            button_row.addWidget(button)
        button_row.addStretch()
        elayout.addLayout(button_row)
        elayout.addStretch()
        splitter.addWidget(editor)
        splitter.setSizes([280, 620])
        outer.addWidget(splitter, 1)
        return panel

    # === Data / refresh ====================================================

    def refresh(self) -> None:
        self._all_items = build_voice_items(
            self.ctrl.all_voice_profiles(), self.ctrl.all_designed_voices()
        )
        self._sync_filter_combo(self.clone_project, "clone", list_projects)
        self._sync_filter_combo(self.clone_tag, "clone", list_tags)
        self._sync_filter_combo(self.design_project, "design", list_projects)
        self._sync_filter_combo(self.design_tag, "design", list_tags)
        self._refresh_clone_list()
        self._refresh_design_list()

    def _items_of_kind(self, kind: str):
        return filter_voice_items(self._all_items, kinds=(kind,))

    def _sync_filter_combo(self, combo: QComboBox, kind: str, source) -> None:
        current = combo.currentText() if combo.count() else _ALL
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(_ALL)
        for value in source(self._items_of_kind(kind)):
            combo.addItem(value)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _refresh_clone_list(self) -> None:
        self._fill_list(
            self.profile_list,
            self._filtered("clone", self.clone_search, self.clone_project, self.clone_tag),
        )

    def _refresh_design_list(self) -> None:
        self._fill_list(
            self.design_list,
            self._filtered("design", self.design_search, self.design_project, self.design_tag),
        )

    def _filtered(self, kind, search, project_combo, tag_combo):
        project = project_combo.currentText() if project_combo.currentIndex() > 0 else None
        tag = tag_combo.currentText() if tag_combo.currentIndex() > 0 else None
        return filter_voice_items(
            self._all_items,
            query=search.text(),
            project=project,
            tag=tag,
            kinds=(kind,),
        )

    @staticmethod
    def _fill_list(widget: QListWidget, items) -> None:
        selected = widget.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        widget.blockSignals(True)
        widget.clear()
        for item in items:
            suffix = f" · {item.subtitle}" if item.subtitle else ""
            row = QListWidgetItem(f"{item.name}{suffix}")
            row.setData(Qt.ItemDataRole.UserRole, item.item_id)
            widget.addItem(row)
            if item.item_id == selected_id:
                widget.setCurrentItem(row)
        widget.blockSignals(False)

    # === Clone editor actions =============================================

    def _on_profile_selected(self, current, _previous) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = next(
            (p for p in self.ctrl.all_voice_profiles() if p.profile_id == profile_id), None
        )
        if profile is None:
            return
        self._editing_id = profile.profile_id
        self.name_edit.setText(profile.name)
        self._audio_path = Path(profile.audio_path) if profile.audio_path else None
        self.audio_edit.setText(str(profile.audio_path or ""))
        self.audio_preview_button.setEnabled(self._audio_path is not None)
        self.audio_meta.setText(
            f"{profile.duration_seconds:.1f}s · {profile.sample_rate} Hz"
            if profile.duration_seconds else ""
        )
        self.project_edit.setText(profile.project)
        self.tags_edit.setText(", ".join(profile.tags))
        index = self.language_combo.findData(profile.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.transcript_edit.setPlainText(profile.transcript)
        self.notes_edit.setPlainText(profile.notes)
        self._load_samples(profile)

    def _load_samples(self, profile) -> None:
        samples = profile.extra_samples or []
        self.samples_table.setRowCount(len(samples))
        for row, sample in enumerate(samples):
            is_default = "★" if sample.sample_id == profile.default_sample_id else ""
            duration = f"{sample.duration_seconds:.1f}s" if sample.duration_seconds else ""
            for column, value in enumerate([is_default, sample.role, duration, sample.transcript or ""]):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, sample.sample_id)
                self.samples_table.setItem(row, column, cell)

    def _pick_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn audio mẫu", "", _AUDIO_FILTER)
        if path:
            self._audio_path = Path(path)
            self.audio_edit.setText(path)
            self.audio_preview_button.setEnabled(True)

    def _clear_editor(self) -> None:
        self._editing_id = None
        self._audio_path = None
        self.name_edit.clear()
        self.audio_edit.clear()
        self.audio_preview_button.setEnabled(False)
        self.audio_meta.clear()
        self.project_edit.clear()
        self.tags_edit.clear()
        self.transcript_edit.clear()
        self.notes_edit.clear()
        self.samples_table.setRowCount(0)
        self.profile_list.clearSelection()

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.information(self, "Thiếu tên", "Hãy nhập tên profile.")
            return
        if self._audio_path is None:
            QMessageBox.information(self, "Thiếu audio", "Hãy chọn audio mẫu.")
            return
        try:
            _profile, warnings = self.ctrl.save_voice_profile(
                name=name,
                audio_path=self._audio_path,
                transcript=self.transcript_edit.toPlainText().strip(),
                language=str(self.language_combo.currentData()),
                project=self.project_edit.text().strip(),
                notes=self.notes_edit.toPlainText().strip(),
                profile_id=self._editing_id,
                tags=_parse_tags(self.tags_edit.text()),
            )
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
            return
        if warnings:
            QMessageBox.warning(self, "Đã lưu (có cảnh báo)", "\n".join(w.message for w in warnings))
        self.context.log(f"Đã lưu profile giọng: {name}")
        self.refresh()

    def _delete(self) -> None:
        if not self._editing_id:
            return
        if QMessageBox.question(self, "Xóa profile", "Xóa profile giọng này?") != QMessageBox.StandardButton.Yes:
            return
        self.ctrl.delete_voice_profile(self._editing_id)
        self.context.log("Đã xóa profile giọng.")
        self._clear_editor()
        self.refresh()

    # --- Preview + samples (clone) -----------------------------------------

    def _play(self, action) -> None:
        try:
            path = action()
        except Exception as error:
            QMessageBox.warning(self, "Không phát được audio", str(error))
            return
        self.context.log(f"Đã mở audio bằng ứng dụng mặc định: {path}")

    def _preview_profile_item(self, item) -> None:
        profile_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if profile_id:
            self._play(lambda: self.ctrl.play_voice_profile_sample(profile_id))

    def _preview_main_sample(self) -> None:
        if self._audio_path is None:
            return
        self._play(lambda: self.ctrl.play_audio_file(self._audio_path))

    def _preview_selected_sample(self, *_args) -> None:
        sample_id = self._selected_sample_id()
        if not self._editing_id or not sample_id:
            QMessageBox.information(self, "Chưa chọn mẫu", "Hãy chọn một mẫu phụ trong bảng.")
            return
        self._play(
            lambda: self.ctrl.play_voice_profile_sample(self._editing_id, sample_id)
        )

    def _selected_sample_id(self) -> str | None:
        row = self.samples_table.currentRow()
        if row < 0:
            return None
        cell = self.samples_table.item(row, 0)
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def _add_sample(self) -> None:
        if not self._editing_id:
            QMessageBox.information(self, "Chưa lưu profile", "Hãy lưu profile trước khi thêm mẫu phụ.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Chọn mẫu phụ", "", _AUDIO_FILTER)
        if not path:
            return
        try:
            self.ctrl.add_voice_profile_sample(
                profile_id=self._editing_id,
                audio_path=Path(path),
                role=self.role_combo.currentText(),
            )
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
            return
        self._reselect()

    def _remove_sample(self) -> None:
        if not self._editing_id:
            return
        row = self.samples_table.currentRow()
        if row < 0:
            return
        try:
            self.ctrl.remove_voice_profile_sample(self._editing_id, row)
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
            return
        self._reselect()

    def _set_default_sample(self) -> None:
        sample_id = self._selected_sample_id()
        if not self._editing_id or not sample_id:
            return
        try:
            self.ctrl.set_voice_profile_default_sample(self._editing_id, sample_id)
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
            return
        self._reselect()

    def _reselect(self) -> None:
        editing = self._editing_id
        self.refresh()
        for row in range(self.profile_list.count()):
            item = self.profile_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == editing:
                self.profile_list.setCurrentItem(item)
                break

    # === Design editor actions ============================================

    def _on_design_selected(self, current, _previous) -> None:
        if current is None:
            return
        voice_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            voice = self.ctrl.designed_voice(voice_id)
        except Exception:
            return
        self._design_editing_id = voice.designed_voice_id
        self.design_name.setText(voice.name)
        self.design_instruct.setPlainText(voice.instruct)
        self.design_project_edit.setText(voice.project)
        self.design_tags_edit.setText(", ".join(voice.tags))
        index = self.design_language.findData(voice.language)
        if index >= 0:
            self.design_language.setCurrentIndex(index)
        self.design_notes.setPlainText(voice.notes)

    def _clear_design_editor(self) -> None:
        self._design_editing_id = None
        self.design_name.clear()
        self.design_instruct.clear()
        self.design_project_edit.clear()
        self.design_tags_edit.clear()
        self.design_notes.clear()
        self.design_list.clearSelection()

    def _save_design(self) -> None:
        name = self.design_name.text().strip()
        instruct = self.design_instruct.toPlainText().strip()
        if not name:
            QMessageBox.information(self, "Thiếu tên", "Hãy nhập tên giọng thiết kế.")
            return
        if not instruct:
            QMessageBox.information(self, "Thiếu mô tả", "Hãy nhập mô tả giọng (instruct).")
            return
        try:
            voice = self.ctrl.save_designed_voice(
                name=name,
                instruct=instruct,
                language=str(self.design_language.currentData()),
                project=self.design_project_edit.text().strip(),
                tags=_parse_tags(self.design_tags_edit.text()),
                notes=self.design_notes.toPlainText().strip(),
                voice_id=self._design_editing_id,
            )
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
            return
        self._design_editing_id = voice.designed_voice_id
        self.context.log(f"Đã lưu giọng thiết kế: {name}")
        self.refresh()

    def _delete_design(self) -> None:
        if not self._design_editing_id:
            return
        if QMessageBox.question(self, "Xóa giọng thiết kế", "Xóa giọng thiết kế này?") != QMessageBox.StandardButton.Yes:
            return
        self.ctrl.delete_designed_voice(self._design_editing_id)
        self.context.log("Đã xóa giọng thiết kế.")
        self._clear_design_editor()
        self.refresh()
