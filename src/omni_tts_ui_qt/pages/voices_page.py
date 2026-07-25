"""Voice profile manager: list, editor, extra samples."""

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
    QVBoxLayout,
    QWidget,
)

from omni_tts_ui_qt.context import AppContext

_LANGUAGES = [("vi — Tiếng Việt", "vi"), ("en — English", "en"), ("zh", "zh"), ("ja", "ja"), ("ko", "ko")]
_ROLES = ["neutral", "storytelling", "news", "emotional", "fast", "slow"]
_AUDIO_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)"


class VoicesPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._editing_id: str | None = None
        self._audio_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Profile giọng")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_editor())
        splitter.setSizes([280, 620])
        layout.addWidget(splitter, 1)
        self.refresh()

    def _build_list(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        refresh = QPushButton("Làm mới")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(self.profile_list, 1)
        layout.addWidget(refresh)
        panel.setMinimumWidth(240)
        return panel

    def _build_editor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        audio_row = QHBoxLayout()
        self.audio_edit = QLineEdit()
        self.audio_edit.setReadOnly(True)
        pick = QPushButton("Chọn…")
        pick.clicked.connect(self._pick_audio)
        audio_row.addWidget(self.audio_edit, 1)
        audio_row.addWidget(pick)
        self.audio_meta = QLabel("")
        self.audio_meta.setObjectName("hint")
        self.project_edit = QLineEdit()
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
        self.samples_table.setMaximumHeight(140)
        layout.addWidget(self.samples_table)
        sample_row = QHBoxLayout()
        self.role_combo = QComboBox()
        self.role_combo.addItems(_ROLES)
        add_sample = QPushButton("Thêm mẫu phụ")
        remove_sample = QPushButton("Xóa mẫu chọn")
        default_sample = QPushButton("Đặt làm mặc định")
        add_sample.clicked.connect(self._add_sample)
        remove_sample.clicked.connect(self._remove_sample)
        default_sample.clicked.connect(self._set_default_sample)
        sample_row.addWidget(QLabel("Vai trò:"))
        sample_row.addWidget(self.role_combo)
        sample_row.addWidget(add_sample)
        sample_row.addWidget(remove_sample)
        sample_row.addWidget(default_sample)
        sample_row.addStretch()
        layout.addLayout(sample_row)
        return panel

    # --- List ---------------------------------------------------------------

    def refresh(self) -> None:
        self.profile_list.clear()
        for profile in self.ctrl.all_voice_profiles():
            duration = f" · {profile.duration_seconds:.1f}s" if profile.duration_seconds else ""
            item = QListWidgetItem(f"{profile.name}  ({profile.language}){duration}")
            item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
            self.profile_list.addItem(item)

    def _on_profile_selected(self, current, _previous) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = next((p for p in self.ctrl.all_voice_profiles() if p.profile_id == profile_id), None)
        if profile is None:
            return
        self._editing_id = profile.profile_id
        self.name_edit.setText(profile.name)
        self._audio_path = Path(profile.audio_path) if profile.audio_path else None
        self.audio_edit.setText(str(profile.audio_path or ""))
        self.audio_meta.setText(
            f"{profile.duration_seconds:.1f}s · {profile.sample_rate} Hz"
            if profile.duration_seconds else ""
        )
        self.project_edit.setText(profile.project)
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

    # --- Editor actions -----------------------------------------------------

    def _pick_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn audio mẫu", "", _AUDIO_FILTER)
        if path:
            self._audio_path = Path(path)
            self.audio_edit.setText(path)

    def _clear_editor(self) -> None:
        self._editing_id = None
        self._audio_path = None
        self.name_edit.clear()
        self.audio_edit.clear()
        self.audio_meta.clear()
        self.project_edit.clear()
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
