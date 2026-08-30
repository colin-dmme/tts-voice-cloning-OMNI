"""Central pronunciation-preset manager.

This page only binds Qt widgets to AppController. Matching, conflict handling,
validation, persistence, and statistics remain in the core pronunciation layer.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
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

from omni_tts_core.ui_presenters.pronunciation import (
    analysis_details,
    analysis_summary,
    preset_label,
)
from omni_tts_shared.pronunciation import PronunciationRule, PronunciationSelection
from omni_tts_ui_qt.context import AppContext


class PronunciationPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._editing_id: str | None = None
        self._presets = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Cách đọc / Từ điển phát âm")
        title.setObjectName("pageTitle")
        hint = QLabel(
            "Từ gốc luôn được giữ trong văn bản và subtitle; chỉ bản gửi tới model "
            "TTS mới dùng cách đọc đã cấu hình."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_library())
        splitter.addWidget(self._build_editor())
        splitter.setSizes([300, 850])
        layout.addWidget(splitter, 1)
        self.refresh()

    def _build_library(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm preset, dự án, tag…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_list)
        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(self._on_selected)
        layout.addWidget(self.search)
        layout.addWidget(self.preset_list, 1)

        row = QHBoxLayout()
        new_button = QPushButton("Tạo mới")
        duplicate_button = QPushButton("Nhân bản")
        delete_button = QPushButton("Xóa")
        new_button.clicked.connect(self._clear_editor)
        duplicate_button.clicked.connect(self._duplicate)
        delete_button.clicked.connect(self._delete)
        row.addWidget(new_button)
        row.addWidget(duplicate_button)
        row.addWidget(delete_button)
        layout.addLayout(row)

        io_row = QHBoxLayout()
        import_button = QPushButton("Nhập JSON…")
        export_button = QPushButton("Xuất JSON…")
        import_button.clicked.connect(self._import)
        export_button.clicked.connect(self._export)
        io_row.addWidget(import_button)
        io_row.addWidget(export_button)
        layout.addLayout(io_row)
        panel.setMinimumWidth(260)
        return panel

    def _build_editor(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.project_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("quảng cáo, dự án A, tên riêng…")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(55)
        form.addRow("Tên preset:", self.name_edit)
        form.addRow("Dự án:", self.project_edit)
        form.addRow("Tag:", self.tags_edit)
        form.addRow("Ghi chú:", self.notes_edit)
        layout.addLayout(form)

        rule_header = QHBoxLayout()
        rule_header.addWidget(QLabel("Danh sách từ"))
        rule_header.addStretch()
        add_rule = QPushButton("+ Thêm từ")
        remove_rule = QPushButton("Xóa dòng chọn")
        add_rule.clicked.connect(lambda: self._add_rule())
        remove_rule.clicked.connect(self._remove_rules)
        rule_header.addWidget(add_rule)
        rule_header.addWidget(remove_rule)
        layout.addLayout(rule_header)

        self.rules_table = QTableWidget(0, 7)
        self.rules_table.setHorizontalHeaderLabels(
            ["Bật", "Từ/cụm từ gốc", "Cách đọc", "Kiểu khớp", "Phân biệt hoa", "Ưu tiên", "Ghi chú"]
        )
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.rules_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rules_table, 1)

        save_row = QHBoxLayout()
        self.revision_label = QLabel("")
        self.revision_label.setObjectName("hint")
        save_button = QPushButton("Lưu preset")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        save_row.addWidget(self.revision_label, 1)
        save_row.addWidget(save_button)
        layout.addLayout(save_row)

        preview_title = QHBoxLayout()
        preview_title.addWidget(QLabel("Kiểm tra cách đọc"))
        preview_title.addStretch()
        preview_button = QPushButton("Phân tích")
        preview_button.clicked.connect(self._preview)
        preview_title.addWidget(preview_button)
        layout.addLayout(preview_title)
        self.preview_input = QPlainTextEdit()
        self.preview_input.setPlaceholderText("Ví dụ: Phân Gà Sinh Học IIKO loại 10 lít")
        self.preview_input.setMaximumHeight(70)
        self.preview_summary = QLabel("Lưu preset rồi nhập văn bản để phân tích.")
        self.preview_summary.setObjectName("hint")
        self.preview_summary.setWordWrap(True)
        self.preview_speech = QPlainTextEdit()
        self.preview_speech.setReadOnly(True)
        self.preview_speech.setPlaceholderText("Văn bản thực tế gửi tới model sẽ hiện ở đây.")
        self.preview_speech.setMaximumHeight(70)
        layout.addWidget(self.preview_input)
        layout.addWidget(self.preview_summary)
        layout.addWidget(self.preview_speech)
        return panel

    def refresh(self) -> None:
        try:
            self._presets = self.ctrl.pronunciation_presets()
        except Exception as error:
            QMessageBox.warning(self, "Không đọc được preset", str(error))
            self._presets = []
        self._refresh_list()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _refresh_list(self) -> None:
        selected_id = self._editing_id
        needle = self.search.text().strip().casefold()
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        selected_item = None
        for preset in self._presets:
            haystack = " ".join(
                [preset.name, preset.project, *preset.tags, preset.notes]
            ).casefold()
            if needle and needle not in haystack:
                continue
            item = QListWidgetItem(preset_label(preset))
            item.setData(Qt.ItemDataRole.UserRole, preset.preset_id)
            item.setToolTip(
                f"Revision {preset.revision} · {len(preset.rules)} quy tắc"
            )
            self.preset_list.addItem(item)
            if preset.preset_id == selected_id:
                selected_item = item
        self.preset_list.blockSignals(False)
        if selected_item is not None:
            self.preset_list.setCurrentItem(selected_item)

    def _on_selected(self, current: QListWidgetItem | None, _previous=None) -> None:
        preset_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if not preset_id:
            return
        try:
            preset = self.ctrl.pronunciation_preset(str(preset_id))
        except Exception as error:
            QMessageBox.warning(self, "Không mở được preset", str(error))
            return
        self._editing_id = preset.preset_id
        self.name_edit.setText(preset.name)
        self.project_edit.setText(preset.project)
        self.tags_edit.setText(", ".join(preset.tags))
        self.notes_edit.setPlainText(preset.notes)
        self.rules_table.setRowCount(0)
        for rule in preset.rules:
            self._add_rule(rule)
        self.revision_label.setText(
            f"Revision {preset.revision} · cập nhật {preset.updated_at or '—'}"
        )

    def _add_rule(self, rule: PronunciationRule | None = None) -> None:
        row = self.rules_table.rowCount()
        self.rules_table.insertRow(row)
        enabled = QCheckBox()
        enabled.setChecked(True if rule is None else rule.enabled)
        self.rules_table.setCellWidget(row, 0, enabled)
        self.rules_table.setItem(row, 1, QTableWidgetItem(rule.written if rule else ""))
        self.rules_table.setItem(row, 2, QTableWidgetItem(rule.spoken if rule else ""))
        mode = QComboBox()
        mode.addItem("Nguyên từ/cụm", "whole_term")
        mode.addItem("Chuỗi ký tự", "literal")
        if rule is not None:
            index = mode.findData(rule.match_mode)
            if index >= 0:
                mode.setCurrentIndex(index)
        self.rules_table.setCellWidget(row, 3, mode)
        case = QCheckBox()
        case.setChecked(False if rule is None else rule.case_sensitive)
        self.rules_table.setCellWidget(row, 4, case)
        self.rules_table.setItem(
            row, 5, QTableWidgetItem(str(rule.priority if rule else 0))
        )
        self.rules_table.setItem(row, 6, QTableWidgetItem(rule.notes if rule else ""))
        self.rules_table.setCurrentCell(row, 1)

    def _remove_rules(self) -> None:
        rows = sorted({index.row() for index in self.rules_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.rules_table.removeRow(row)

    def _collect_rules(self) -> list[PronunciationRule]:
        rules = []
        for row in range(self.rules_table.rowCount()):
            written = self._cell_text(row, 1)
            spoken = self._cell_text(row, 2)
            if not written and not spoken:
                continue
            enabled = self.rules_table.cellWidget(row, 0)
            mode = self.rules_table.cellWidget(row, 3)
            case = self.rules_table.cellWidget(row, 4)
            try:
                priority = int(self._cell_text(row, 5) or 0)
            except ValueError as exc:
                raise ValueError(f"Dòng {row + 1}: ưu tiên phải là số nguyên.") from exc
            rules.append(
                PronunciationRule(
                    written=written,
                    spoken=spoken,
                    enabled=bool(enabled and enabled.isChecked()),
                    match_mode=str(mode.currentData() if mode else "whole_term"),
                    case_sensitive=bool(case and case.isChecked()),
                    priority=priority,
                    notes=self._cell_text(row, 6),
                )
            )
        return rules

    def _cell_text(self, row: int, column: int) -> str:
        item = self.rules_table.item(row, column)
        return item.text().strip() if item else ""

    def _save(self) -> None:
        try:
            preset = self.ctrl.save_pronunciation_preset(
                name=self.name_edit.text(),
                project=self.project_edit.text(),
                tags=[part.strip() for part in self.tags_edit.text().split(",") if part.strip()],
                notes=self.notes_edit.toPlainText(),
                rules=self._collect_rules(),
                preset_id=self._editing_id,
            )
        except Exception as error:
            QMessageBox.warning(self, "Không lưu được preset", str(error))
            return
        self._editing_id = preset.preset_id
        self.context.log(f"Đã lưu preset cách đọc: {preset.name} (revision {preset.revision}).")
        self.refresh()

    def _clear_editor(self) -> None:
        self._editing_id = None
        self.preset_list.clearSelection()
        self.name_edit.clear()
        self.project_edit.clear()
        self.tags_edit.clear()
        self.notes_edit.clear()
        self.rules_table.setRowCount(0)
        self.revision_label.setText("Preset mới chưa lưu")
        self.preview_summary.setText("Lưu preset rồi bấm Phân tích.")
        self.preview_speech.clear()
        self._add_rule()

    def _delete(self) -> None:
        if not self._editing_id:
            return
        if QMessageBox.question(
            self,
            "Xóa preset cách đọc",
            "Xóa preset đang chọn? Các hàng đợi đã ghim preset này sẽ cần chọn lại.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.ctrl.delete_pronunciation_preset(self._editing_id)
        except Exception as error:
            QMessageBox.warning(self, "Không xóa được preset", str(error))
            return
        self._clear_editor()
        self.refresh()

    def _duplicate(self) -> None:
        if not self._editing_id:
            return
        try:
            preset = self.ctrl.duplicate_pronunciation_preset(self._editing_id)
        except Exception as error:
            QMessageBox.warning(self, "Không nhân bản được preset", str(error))
            return
        self._editing_id = preset.preset_id
        self.refresh()

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Nhập preset cách đọc", "", "JSON (*.json)"
        )
        if not filename:
            return
        try:
            preset = self.ctrl.import_pronunciation_preset(Path(filename))
        except Exception as error:
            QMessageBox.warning(self, "Không nhập được preset", str(error))
            return
        self._editing_id = preset.preset_id
        self.refresh()

    def _export(self) -> None:
        if not self._editing_id:
            QMessageBox.information(self, "Chưa chọn preset", "Hãy chọn preset cần xuất.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Xuất preset cách đọc", f"{self.name_edit.text() or 'pronunciation'}.json", "JSON (*.json)"
        )
        if not filename:
            return
        try:
            self.ctrl.export_pronunciation_preset(self._editing_id, Path(filename))
        except Exception as error:
            QMessageBox.warning(self, "Không xuất được preset", str(error))

    def _preview(self) -> None:
        if not self._editing_id:
            QMessageBox.information(self, "Preset chưa lưu", "Hãy lưu preset trước khi phân tích.")
            return
        try:
            analysis = self.ctrl.preview_pronunciation(
                self.preview_input.toPlainText(),
                PronunciationSelection(enabled=True, preset_ids=[self._editing_id]),
            )
        except Exception as error:
            QMessageBox.warning(self, "Không phân tích được", str(error))
            return
        details = analysis_details(analysis, limit=20)
        summary = analysis_summary(analysis)
        self.preview_summary.setText(f"{summary}\n{details}" if details else summary)
        self.preview_speech.setPlainText(analysis.speech_text)