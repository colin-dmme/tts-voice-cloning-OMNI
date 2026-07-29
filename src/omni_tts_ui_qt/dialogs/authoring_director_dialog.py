from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.authoring.schemas import (
    AuthoringBrief,
    AuthoringCandidate,
    VoiceContext,
)
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.background import AuthoringWorker
from omni_tts_ui_qt.context import AppContext


class AuthoringDirectorDialog(QDialog):
    """Collect a reusable brief, generate variants, compare, then apply."""

    def __init__(
        self,
        context: AppContext,
        *,
        source_text: str,
        settings: GenerationSettings,
        dialect_id: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.ctrl = context.controller
        self.source_text = source_text
        self.settings = settings
        self.dialect_id = dialect_id
        self.selected_text = ""
        self._worker: AuthoringWorker | None = None
        self._closing_after_cancel = False
        self._tab_candidates: list[AuthoringCandidate] = []
        self.setWindowTitle("AI đạo diễn · Tạo phương án thể hiện")
        self.setMinimumSize(1080, 720)
        self._build()
        self._load_state()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        lead = QLabel(
            "AI tạo Performance Plan trung lập từ nội dung và profile giọng; "
            "ứng dụng mới chuyển plan sang cú pháp của provider."
        )
        lead.setWordWrap(True)
        lead.setObjectName("hint")
        outer.addWidget(lead)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_brief_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 680])
        outer.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("hint")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.cancel_generation = QPushButton("Hủy phân tích")
        self.cancel_generation.setEnabled(False)
        self.regenerate_button = QPushButton("Tạo thêm từ setting này")
        self.regenerate_button.setEnabled(False)
        self.apply_button = QPushButton("Áp dụng phương án")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setEnabled(False)
        close_button = QPushButton("Đóng")
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.progress)
        footer.addWidget(self.cancel_generation)
        footer.addWidget(self.regenerate_button)
        footer.addWidget(self.apply_button)
        footer.addWidget(close_button)
        outer.addLayout(footer)

        self.generate_button.clicked.connect(lambda: self._generate())
        self.cancel_generation.clicked.connect(self._cancel_generation)
        self.regenerate_button.clicked.connect(self._regenerate)
        self.apply_button.clicked.connect(self._apply_selected)
        close_button.clicked.connect(self.reject)

    def _build_brief_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)

        preset_group = QGroupBox("Preset")
        preset_layout = QHBoxLayout(preset_group)
        self.preset_combo = QComboBox()
        self.save_preset_button = QPushButton("Lưu preset")
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.save_preset_button)
        layout.addWidget(preset_group)
        self.save_preset_button.clicked.connect(self._save_preset)
        self.preset_combo.currentIndexChanged.connect(self._apply_selected_preset)

        brief_group = QGroupBox("Ngữ cảnh nội dung")
        form = QFormLayout(brief_group)
        choices = self.ctrl.authoring_brief_choices()
        self.content_type = self._choice_combo(choices["content_type"])
        self.platform = self._choice_combo(choices["platform"])
        self.segment_role = self._choice_combo(choices["segment_role"])
        self.narrator_style = self._choice_combo(choices["narrator_style"])
        self.tag_density = self._choice_combo(choices["tag_density"])
        self.audience = QLineEdit()
        self.audience.setPlaceholderText("Ví dụ: người xem phổ thông yêu khoa học")
        form.addRow("Loại nội dung:", self.content_type)
        form.addRow("Nền tảng:", self.platform)
        form.addRow("Vai trò đoạn:", self.segment_role)
        form.addRow("Phong cách đọc:", self.narrator_style)
        form.addRow("Mật độ điều khiển:", self.tag_density)
        form.addRow("Đối tượng nghe:", self.audience)
        layout.addWidget(brief_group)

        voice_group = QGroupBox("AI hiểu profile giọng")
        voice_form = QFormLayout(voice_group)
        self.voice_summary = QLabel("")
        self.voice_summary.setWordWrap(True)
        self.voice_presentation = self._choice_combo(
            choices["voice_presentation"]
        )
        self.voice_description = QPlainTextEdit()
        self.voice_description.setMaximumHeight(90)
        self.voice_description.setPlaceholderText(
            "Ví dụ: nữ trưởng thành, ấm, rõ, thuyết minh khoa học tự nhiên…"
        )
        voice_form.addRow("Giọng đang chọn:", self.voice_summary)
        voice_form.addRow("Nam / nữ:", self.voice_presentation)
        voice_form.addRow("Mô tả bổ sung:", self.voice_description)
        layout.addWidget(voice_group)

        rules_group = QGroupBox("Quy tắc và thử nghiệm")
        rules = QVBoxLayout(rules_group)
        self.preserve_wording = QCheckBox(
            "Giữ nguyên từng chữ · bắt buộc ở phiên bản này"
        )
        self.preserve_wording.setChecked(True)
        self.preserve_wording.setEnabled(False)
        self.preserve_wording.setToolTip(
            "AI chỉ ra quyết định diễn; renderer dùng lại nguyên văn nguồn."
        )
        self.allow_punctuation = QCheckBox(
            "Chuẩn hóa dấu câu · dành cho phiên bản sau"
        )
        self.allow_punctuation.setEnabled(False)
        self.allow_punctuation.setToolTip(
            "Kiến trúc đã lưu tùy chọn này; phiên bản hiện tại vẫn ưu tiên nguyên văn."
        )
        self.allow_sfx = QCheckBox("Cho phép SFX giọng nói khi có cue nguyên văn")
        count_row = QHBoxLayout()
        self.candidate_count = QSpinBox()
        self.candidate_count.setRange(1, 4)
        self.candidate_count.setValue(2)
        count_row.addWidget(QLabel("Số phương án:"))
        count_row.addWidget(self.candidate_count)
        count_row.addStretch()
        self.extra_direction = QPlainTextEdit()
        self.extra_direction.setMaximumHeight(90)
        self.extra_direction.setPlaceholderText(
            "Chỉ dẫn riêng, ví dụ: đây là hook khoa học, tò mò nhưng không cường điệu."
        )
        rules.addWidget(self.preserve_wording)
        rules.addWidget(self.allow_punctuation)
        rules.addWidget(self.allow_sfx)
        rules.addLayout(count_row)
        rules.addWidget(QLabel("Chỉ dẫn bổ sung:"))
        rules.addWidget(self.extra_direction)
        layout.addWidget(rules_group)

        self.generate_button = QPushButton("✨ Phân tích và tạo phương án")
        self.generate_button.setObjectName("primaryButton")
        layout.addWidget(self.generate_button)
        layout.addStretch()
        return panel

    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel("Các phương án"))
        self.history_combo = QComboBox()
        self.load_history_button = QPushButton("Nạp lần trước")
        self.load_history_button.clicked.connect(self._load_selected_history)
        header.addWidget(self.history_combo, 1)
        header.addWidget(self.load_history_button)
        header.addStretch()
        self.original_button = QPushButton("Xem bản gốc")
        self.original_button.clicked.connect(self._show_original)
        header.addWidget(self.original_button)
        layout.addLayout(header)
        self.result_tabs = QTabWidget()
        self.result_tabs.currentChanged.connect(self._sync_candidate_actions)
        layout.addWidget(self.result_tabs, 1)
        placeholder = QLabel(
            "Chưa có phương án. Setting và kết quả từng lần chạy sẽ được lưu "
            "để có thể tạo lại hoặc so sánh."
        )
        placeholder.setWordWrap(True)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_tabs.addTab(placeholder, "Hướng dẫn")
        return panel

    @staticmethod
    def _choice_combo(options) -> QComboBox:
        combo = QComboBox()
        for option in options:
            combo.addItem(option.label, option.value)
            combo.setItemData(
                combo.count() - 1,
                option.tooltip,
                Qt.ItemDataRole.ToolTipRole,
            )
        return combo

    def _load_state(self) -> None:
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Thiết lập gần nhất", self.ctrl.last_authoring_brief())
        preferred_index = 0
        for preset in self.ctrl.authoring_presets():
            self.preset_combo.addItem(preset.name, preset.brief)
            if (
                preset.voice_profile_id
                and preset.voice_profile_id == (self.settings.voice_profile_id or "")
                and (not preset.dialect_id or preset.dialect_id == self.dialect_id)
            ):
                preferred_index = self.preset_combo.count() - 1
                self.preset_combo.setItemData(
                    preferred_index,
                    "Preset đã lưu cho profile giọng đang chọn.",
                    Qt.ItemDataRole.ToolTipRole,
                )
        self.preset_combo.blockSignals(False)
        self.preset_combo.setCurrentIndex(preferred_index)
        selected_brief = self.preset_combo.currentData()
        self._set_brief(
            selected_brief
            if isinstance(selected_brief, AuthoringBrief)
            else self.ctrl.last_authoring_brief()
        )
        try:
            voice = self.ctrl.resolve_authoring_voice_context(self.settings)
        except Exception:
            voice = VoiceContext(display_name="Giọng đang chọn")
        self.voice_summary.setText(voice.summary)
        self._set_combo(self.voice_presentation, voice.presentation)
        self.voice_description.setPlainText(voice.description)
        self._load_history_choices()

    def _current_brief(self) -> AuthoringBrief:
        return AuthoringBrief(
            content_type=str(self.content_type.currentData()),
            platform=str(self.platform.currentData()),
            segment_role=str(self.segment_role.currentData()),
            target_audience=self.audience.text(),
            narrator_style=str(self.narrator_style.currentData()),
            tag_density=str(self.tag_density.currentData()),
            preserve_wording=self.preserve_wording.isChecked(),
            allow_punctuation_changes=self.allow_punctuation.isChecked(),
            allow_vocal_sfx=self.allow_sfx.isChecked(),
            candidate_count=self.candidate_count.value(),
            extra_direction=self.extra_direction.toPlainText(),
        )

    def _set_brief(self, brief: AuthoringBrief) -> None:
        self._set_combo(self.content_type, brief.content_type)
        self._set_combo(self.platform, brief.platform)
        self._set_combo(self.segment_role, brief.segment_role)
        self._set_combo(self.narrator_style, brief.narrator_style)
        self._set_combo(self.tag_density, brief.tag_density)
        self.audience.setText(brief.target_audience)
        self.preserve_wording.setChecked(True)
        self.allow_punctuation.setChecked(False)
        self.allow_sfx.setChecked(brief.allow_vocal_sfx)
        self.candidate_count.setValue(brief.candidate_count)
        self.extra_direction.setPlainText(brief.extra_direction)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_selected_preset(self, index: int) -> None:
        brief = self.preset_combo.itemData(index)
        if isinstance(brief, AuthoringBrief):
            self._set_brief(brief)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Lưu preset",
            "Tên preset:",
        )
        if not ok or not name.strip():
            return
        preset = self.ctrl.save_authoring_preset(
            name,
            self._current_brief(),
            voice_profile_id=self.settings.voice_profile_id or "",
            dialect_id=self.dialect_id,
        )
        self.preset_combo.addItem(preset.name, preset.brief)
        self.preset_combo.setCurrentIndex(self.preset_combo.count() - 1)
        self.context.log(f"Đã lưu preset AI: {preset.name}")

    def _load_history_choices(self) -> None:
        self.history_combo.clear()
        sessions = self.ctrl.recent_authoring_sessions(
            source_text=self.source_text,
            dialect_id=self.dialect_id,
            limit=20,
        )
        for session in sessions:
            self.history_combo.addItem(
                f"{session.created_at.replace('T', ' ')} · "
                f"{len(session.candidates)} phương án",
                session,
            )
        self.load_history_button.setEnabled(bool(sessions))

    def _load_selected_history(self) -> None:
        session = self.history_combo.currentData()
        if session is None:
            return
        if self.result_tabs.count() == 1 and not self._tab_candidates:
            self.result_tabs.clear()
        for candidate in session.candidates:
            self._add_candidate(candidate)
        self.status_label.setText(
            f"Đã nạp lịch sử {session.created_at.replace('T', ' ')}."
        )

    def _generate(self, *, parent_candidate_id: str = "") -> None:
        if self._worker is not None:
            return
        presentation = str(self.voice_presentation.currentData())
        try:
            voice = self.ctrl.resolve_authoring_voice_context(
                self.settings,
                presentation=presentation,
                description=self.voice_description.toPlainText(),
                remember=True,
            )
        except Exception as error:
            QMessageBox.warning(self, "Không đọc được profile giọng", str(error))
            return
        self.voice_summary.setText(voice.summary)
        brief = self._current_brief()
        self._set_running(True)
        self._worker = AuthoringWorker(
            self.ctrl,
            source_text=self.source_text,
            brief=brief,
            voice_context=voice,
            dialect_id=self.dialect_id,
            parent_candidate_id=parent_candidate_id,
            parent=self,
        )
        self._worker.notice.connect(self._on_notice)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _regenerate(self) -> None:
        candidate = self._current_candidate()
        self._generate(
            parent_candidate_id=candidate.candidate_id if candidate else ""
        )

    def _cancel_generation(self) -> None:
        if self._worker:
            self._worker.request_cancel()
            self.status_label.setText("Đang hủy sau request hiện tại…")

    def _on_notice(self, message: str) -> None:
        self.status_label.setText(message)
        self.context.log(message)

    def _on_completed(self, session) -> None:
        if self.result_tabs.count() == 1 and not self._tab_candidates:
            self.result_tabs.clear()
        for candidate in session.candidates:
            self._add_candidate(candidate)
        self.status_label.setText(
            f"Đã tạo {len(session.candidates)} phương án; "
            f"tổng đang giữ {len(self._tab_candidates)}."
        )
        self.context.log(self.status_label.text())
        self._load_history_choices()

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Phân tích thất bại")
        QMessageBox.warning(self, "AI Director", message)

    def _on_cancelled(self) -> None:
        self.status_label.setText("Đã hủy phân tích.")

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()
        self._set_running(False)
        if self._closing_after_cancel:
            super().reject()

    def _set_running(self, running: bool) -> None:
        self.generate_button.setEnabled(not running)
        self.cancel_generation.setEnabled(running)
        self.progress.setVisible(running)
        self.regenerate_button.setEnabled(
            not running and bool(self._tab_candidates)
        )
        self.apply_button.setEnabled(not running and self._current_candidate() is not None)

    def _add_candidate(self, candidate: AuthoringCandidate) -> None:
        if any(
            item.candidate_id == candidate.candidate_id
            for item in self._tab_candidates
        ):
            return
        page = QWidget()
        layout = QVBoxLayout(page)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(candidate.rendered_text)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setMaximumHeight(190)
        decision_lines = [
            f"Câu {item.sentence_index + 1}: {item.reason or '(không có lý do)'}"
            for item in candidate.plan.decisions
        ]
        warnings = [
            *candidate.plan.warnings,
            *candidate.validation_messages,
        ]
        detail_text = candidate.plan.summary.strip()
        if decision_lines:
            detail_text += "\n\nQuyết định:\n- " + "\n- ".join(decision_lines)
        if warnings:
            detail_text += "\n\nCảnh báo:\n- " + "\n- ".join(
                dict.fromkeys(warnings)
            )
        details.setPlainText(detail_text.strip() or "Không có ghi chú.")
        layout.addWidget(text, 1)
        layout.addWidget(QLabel("Giải thích và kiểm tra:"))
        layout.addWidget(details)
        self._tab_candidates.append(candidate)
        self.result_tabs.addTab(page, f"PA {len(self._tab_candidates)}")
        self.result_tabs.setCurrentIndex(self.result_tabs.count() - 1)
        self._sync_candidate_actions()

    def _current_candidate(self) -> AuthoringCandidate | None:
        index = self.result_tabs.currentIndex()
        if 0 <= index < len(self._tab_candidates):
            return self._tab_candidates[index]
        return None

    def _sync_candidate_actions(self, *_args) -> None:
        if not hasattr(self, "apply_button"):
            return
        enabled = self._current_candidate() is not None and self._worker is None
        self.apply_button.setEnabled(enabled)
        self.regenerate_button.setEnabled(enabled)

    def _show_original(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Văn bản gốc")
        dialog.resize(800, 560)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(self.source_text)
        close = QPushButton("Đóng")
        close.clicked.connect(dialog.accept)
        layout.addWidget(view, 1)
        layout.addWidget(close)
        dialog.exec()

    def _apply_selected(self) -> None:
        candidate = self._current_candidate()
        if candidate is None:
            return
        self.selected_text = candidate.rendered_text
        self.accept()

    def reject(self) -> None:
        if self._worker is not None:
            self._closing_after_cancel = True
            self._cancel_generation()
            return
        super().reject()
