"""Right-hand settings panel — driven entirely by core model metadata.

Nothing here decides what a model can do. `AppController.control_policy()` says
which controls the selected model honours; this panel only shows/enables them and
sends neutral values for the rest, so a knob is never "fake" (visible but
ignored, or accepted then failing at generation time).

Layout, top to bottom: Cơ bản → Nguồn giọng → Tinh chỉnh riêng (đổi theo
provider) → Đầu ra → Bảo vệ GPU.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.pause_presets import (
    PARAGRAPH_PAUSE_FIELD,
    PAUSE_PRESET_KEYS,
    PUNCTUATION_PAUSE_FIELDS,
)
from omni_tts_core.ui_presenters import control_policy, field_limits, model_groups
from omni_tts_core.ui_presenters.control_policy import (
    NEUTRAL_EMOTION,
    NEUTRAL_PITCH,
    NEUTRAL_SPEED,
    GenerationControlPolicy,
)
from omni_tts_core.ui_presenters.pause_explanations import build_pause_explanation
from omni_tts_core.ui_presenters.settings_state import (
    DEFAULT_GENERATION_PREFERENCES,
    GenerationSettings,
)
from omni_tts_core.ui_presenters.tooltips import tooltip
from omni_tts_ui_qt.context import AppContext
from omni_tts_ui_qt.background import FunctionTask
from omni_tts_ui_qt.pages.higgs_remote_section import HiggsRemoteGroup
from omni_tts_ui_qt.pages.settings_sections import ChatterboxGroup, F5Group, VieneuGroup
from omni_tts_ui_qt.widgets.common import (
    CollapsibleSection,
    PathBar,
    RandomPauseEditor,
    dspin_for,
    make_combo,
    pause_seconds_spin_for,
    spin_for,
)
from omni_tts_ui_qt.widgets.higgs_custom_voice_creator import (
    HiggsCustomVoiceCreator,
)

_AUDIO_FORMATS = [("WAV", "wav"), ("MP3", "mp3")]
_BITRATES = [("128 kbps", 128), ("160 kbps", 160), ("192 kbps", 192), ("256 kbps", 256), ("320 kbps", 320)]
_STATUS_COLORS = {"ok": "#34d399", "warn": "#fbbf24", "error": "#f87171"}


class SettingsPanel(QScrollArea):
    settings_changed = Signal()

    def __init__(self, context: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.ctrl = context.controller
        self.setWidgetResizable(True)
        self.setMinimumWidth(370)
        self._loading = True
        self._policy: GenerationControlPolicy | None = None
        # Model whose provider defaults are currently loaded into the tuning
        # widgets; used to avoid re-seeding on every apply_model() call.
        self._seeded_model_id: str | None = None

        container = QWidget()
        self.setWidget(container)
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)

        self._build_basic()
        self._build_punctuation()
        self._build_voice_source()
        self._build_tuning()
        self._build_output()
        self._build_gpu_safety()
        self._layout.addStretch()

        self._loading = False
        # Start on the default model's provider so the list opens short.
        self._select_model(str(DEFAULT_GENERATION_PREFERENCES["model_id"]))
        self.apply_model(self.current_model_id())

    # --- Section builders ---------------------------------------------------

    def _section(self, title: str, *, expanded: bool = True, active: bool | None = None,
                 active_text: str = "ACTIVE · ĐANG ÁP DỤNG",
                 inactive_text: str = "DEACTIVE · KHÔNG ÁP DỤNG",
                 ) -> tuple[CollapsibleSection, QFormLayout]:
        section = CollapsibleSection(
            title, expanded=expanded, active=active,
            active_text=active_text, inactive_text=inactive_text,
        )
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        section.body_layout.addLayout(form)
        self._layout.addWidget(section)
        return section, form

    def _build_basic(self) -> None:
        _section, form = self._section("Cơ bản")
        self.provider_combo = make_combo(self.ctrl.provider_choices())
        self.provider_combo.setToolTip(tooltip("provider"))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.model_combo = make_combo(self.ctrl.model_choices(self._current_provider_id()))
        self.model_combo.setToolTip(tooltip("model"))
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.model_info = self._hint()
        self.runtime_status = self._hint()
        self.language_combo = QComboBox()
        self.language_combo.setToolTip(tooltip("language"))
        self.device_combo = QComboBox()
        self.device_combo.setToolTip(tooltip("device"))
        self.device_note = self._hint()
        self.speed = dspin_for("speed", NEUTRAL_SPEED)
        self.pitch = dspin_for("pitch_shift", NEUTRAL_PITCH)
        self.chunk_pause = pause_seconds_spin_for(
            "chunk_pause_ms", 120, "chunk_pause"
        )
        paragraph = PARAGRAPH_PAUSE_FIELD
        self.paragraph_pause_editor = RandomPauseEditor(
            paragraph.label,
            paragraph.fixed_field,
            paragraph.minimum_field,
            paragraph.maximum_field,
            DEFAULT_GENERATION_PREFERENCES,
            paragraph.tooltip_key,
        )
        self.max_chunk = spin_for("max_chunk_chars", 220, "max_chunk")
        form.addRow("Nhà cung cấp:", self.provider_combo)
        form.addRow("Model TTS:", self.model_combo)
        form.addRow(self.model_info)
        form.addRow(self.runtime_status)
        form.addRow("Ngôn ngữ:", self.language_combo)
        form.addRow("Thiết bị xử lý:", self.device_combo)
        form.addRow(self.device_note)
        self._speed_row = form.rowCount()
        form.addRow("Tốc độ đọc:", self.speed)
        self._pitch_row = form.rowCount()
        form.addRow("Pitch shift:", self.pitch)
        form.addRow("Nghỉ giữa chunk kỹ thuật (giây):", self.chunk_pause)
        form.addRow(self.paragraph_pause_editor)
        form.addRow("Ký tự tối đa mỗi đoạn nhỏ:", self.max_chunk)
        self._basic_form = form
        self._connect_all(self.language_combo, self.device_combo, self.speed, self.pitch,
                          self.chunk_pause, self.max_chunk)
        self.paragraph_pause_editor.changed.connect(self._emit_changed)
        self.paragraph_pause_editor.changed.connect(self._refresh_pause_tooltips)
        self.chunk_pause.valueChanged.connect(self._refresh_pause_tooltips)

    def _build_punctuation(self) -> None:
        self.punctuation_section, form = self._section(
            "Ngắt nghỉ theo dấu câu",
            expanded=True,
            active=True,
            active_text="ACTIVE · ĐANG ÁP DỤNG",
            inactive_text="DEACTIVE · GIỮ NHỊP MODEL",
        )
        if self.punctuation_section.activation is not None:
            self.punctuation_section.activation.setToolTip(tooltip("punctuation_section"))
        self.punctuation_section.setToolTip(tooltip("punctuation_section"))
        self.punctuation_section.activation_changed.connect(self._emit_changed)
        self.punctuation_section.activation_changed.connect(
            self._refresh_pause_tooltips
        )
        self.punctuation_note = self._hint()
        self.punctuation_note.setText(
            "Bỏ chọn Ngẫu nhiên để dùng một giá trị cố định như trước; bật để Core lấy từng lần nghỉ trong khoảng Min–Max."
        )
        self.punctuation_note.setToolTip(tooltip("punctuation_section"))
        form.addRow(self.punctuation_note)
        preset_row = QHBoxLayout()
        self.pause_preset_combo = QComboBox()
        self.pause_preset_save = QPushButton("Lưu preset…")
        self.pause_preset_delete = QPushButton("Xóa preset")
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.pause_preset_combo, 1)
        preset_row.addWidget(self.pause_preset_save)
        preset_row.addWidget(self.pause_preset_delete)
        form.addRow(preset_row)
        self.pause_editors: dict[str, RandomPauseEditor] = {}
        for spec in PUNCTUATION_PAUSE_FIELDS:
            editor = RandomPauseEditor(
                spec.label,
                spec.fixed_field,
                spec.minimum_field,
                spec.maximum_field,
                DEFAULT_GENERATION_PREFERENCES,
                spec.tooltip_key,
            )
            editor.changed.connect(self._emit_changed)
            editor.changed.connect(self._refresh_pause_tooltips)
            self.pause_editors[spec.key] = editor
            form.addRow(editor)
        self.pause_preset_combo.currentIndexChanged.connect(
            self._apply_selected_pause_preset
        )
        self.pause_preset_save.clicked.connect(self._save_pause_preset)
        self.pause_preset_delete.clicked.connect(self._delete_pause_preset)
        self._refresh_pause_presets()
        reset = QPushButton("Đặt lại toàn bộ khoảng nghỉ mặc định")
        reset.setToolTip(tooltip("punctuation_reset"))
        reset.clicked.connect(self._restore_pause_defaults)
        form.addRow(reset)
        self._refresh_pause_tooltips()

    def _build_voice_source(self) -> None:
        self.voice_section, form = self._section("Nguồn giọng")
        self.mode_group = QButtonGroup(self)
        self.mode_fixed = QRadioButton("Giọng cố định")
        self.mode_fixed.setToolTip(tooltip("voice_mode_fixed"))
        self.mode_profile = QRadioButton("Clone từ Profile")
        self.mode_profile.setToolTip(tooltip("voice_mode_profile"))
        self.mode_group.addButton(self.mode_fixed)
        self.mode_group.addButton(self.mode_profile)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_fixed)
        mode_row.addWidget(self.mode_profile)
        self.mode_holder = QWidget()
        self.mode_holder.setLayout(mode_row)
        self._mode_row = form.rowCount()
        form.addRow("Nguồn giọng:", self.mode_holder)
        self.fixed_voice_combo = QComboBox()
        self.fixed_voice_combo.setToolTip(tooltip("voice_fixed"))
        self._fixed_row = form.rowCount()
        form.addRow("Giọng cố định:", self.fixed_voice_combo)
        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip(tooltip("voice_profile"))
        self._profile_row = form.rowCount()
        form.addRow("Profile giọng:", self.profile_combo)
        self.profile_compat = QLabel("")
        self.profile_compat.setWordWrap(True)
        self._compat_row = form.rowCount()
        form.addRow(self.profile_compat)
        self.voice_status = self._hint()
        form.addRow(self.voice_status)
        self.custom_voice_creator = HiggsCustomVoiceCreator(
            self,
            self.ctrl,
            self.current_settings,
            self._select_created_custom_voice,
        )
        self.create_custom_voice_button = self.custom_voice_creator.button
        self._custom_voice_row = form.rowCount()
        form.addRow(self.create_custom_voice_button)
        self._voice_form = form
        self.mode_fixed.toggled.connect(self._on_voice_mode_changed)
        self.fixed_voice_combo.currentIndexChanged.connect(
            self._on_fixed_voice_changed
        )
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)

    def _build_tuning(self) -> None:
        """One dynamic section holding whichever provider knobs apply."""
        self.tuning_section = CollapsibleSection(
            "Tinh chỉnh riêng", expanded=True, active=True,
            active_text="ACTIVE · ĐANG ÁP DỤNG",
            inactive_text="DEACTIVE · DÙNG MẶC ĐỊNH CỦA MODEL",
        )
        if self.tuning_section.activation is not None:
            self.tuning_section.activation.setToolTip(tooltip("tuning_activation"))
        self.tuning_section.activation_changed.connect(self._emit_changed)
        self.vieneu_group = VieneuGroup()
        self.f5_group = F5Group()
        self.chatterbox_group = ChatterboxGroup()
        self.higgs_remote_group = HiggsRemoteGroup()
        for group in (
            self.vieneu_group,
            self.f5_group,
            self.chatterbox_group,
            self.higgs_remote_group,
        ):
            self.tuning_section.body_layout.addWidget(group)
            self._connect_all(*group.widgets())
        self.higgs_remote_group.check_requested.connect(self._check_higgs_endpoint)
        self.higgs_remote_group.api_flavor.currentIndexChanged.connect(
            self._on_higgs_endpoint_type_changed
        )
        self._layout.addWidget(self.tuning_section)
        # Providers without tuning knobs say so, instead of leaving a silent gap
        # that reads as "the settings failed to load".
        self.tuning_absent = self._hint()
        self._layout.addWidget(self.tuning_absent)

    def _build_output(self) -> None:
        _section, form = self._section("Đầu ra")
        self.output_path = PathBar()
        self.output_path.setToolTip(tooltip("output_dir"))
        self.output_path.changed.connect(self._emit_changed)
        form.addRow(self.output_path)
        self.format_combo = make_combo(_AUDIO_FORMATS, "wav")
        self.format_combo.setToolTip(tooltip("output_format"))
        self.bitrate_combo = make_combo(_BITRATES, 192)
        self.bitrate_combo.setToolTip(tooltip("output_bitrate"))
        form.addRow("Định dạng:", self.format_combo)
        form.addRow("Bitrate MP3:", self.bitrate_combo)
        self.overwrite = QCheckBox("Ghi đè file đã có")
        self.split_output = QCheckBox("Tách mỗi đoạn/dòng SRT thành file riêng")
        self.split_output.setChecked(True)
        self.output_srt = QCheckBox("Xuất kèm SRT")
        self.join_split = QCheckBox("Tạo thêm file audio tổng")
        for box, key in (
            (self.overwrite, "output_overwrite"),
            (self.split_output, "output_split"),
            (self.output_srt, "output_srt"),
            (self.join_split, "output_join"),
        ):
            box.setToolTip(tooltip(key))
            form.addRow(box)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.split_output.toggled.connect(self._on_split_changed)
        self._connect_all(self.bitrate_combo, self.overwrite, self.output_srt, self.join_split)

    def _build_gpu_safety(self) -> None:
        self.gpu_section, form = self._section(
            "Bảo vệ GPU (toàn cục)", expanded=False, active=True,
            active_text="ACTIVE · ĐANG BẢO VỆ", inactive_text="DEACTIVE · CHỈ THEO DÕI",
        )
        if self.gpu_section.activation is not None:
            self.gpu_section.activation.setToolTip(tooltip("gpu_enabled"))
        self.gpu_section.activation_changed.connect(self._emit_changed)
        d = DEFAULT_GENERATION_PREFERENCES
        self.gpu_scope = self._hint()
        form.addRow(self.gpu_scope)
        # (attribute, request field, label, tooltip key)
        self._gpu_rows = (
            ("gpu_start", "gpu_start_temperature_c", "Nhiệt độ bắt đầu (°C):", "gpu_start_temp"),
            ("gpu_abort", "gpu_abort_temperature_c", "Nhiệt độ dừng (°C):", "gpu_abort_temp"),
            ("gpu_sustain", "gpu_abort_temperature_sustain_seconds",
             "Giữ quá ngưỡng (giây):", "gpu_abort_sustain"),
            ("gpu_emergency", "gpu_emergency_temperature_c",
             "Nhiệt độ nguy cấp (°C):", "gpu_emergency_temp"),
            ("gpu_resume", "gpu_resume_temperature_c", "Nhiệt độ chạy lại (°C):", "gpu_resume_temp"),
            ("gpu_cooldown", "gpu_cooldown_max_wait_seconds",
             "Chờ phục hồi tối đa (giây):", "gpu_cooldown_max_wait"),
            ("gpu_min_vram", "gpu_minimum_free_vram_mb",
             "VRAM trống trước khi chạy (MB):", "gpu_start_vram"),
            ("gpu_runtime_vram", "gpu_runtime_minimum_free_vram_mb",
             "VRAM trống khi đang chạy (MB):", "gpu_runtime_vram"),
            ("gpu_max_util", "gpu_maximum_utilization_percent",
             "GPU đang dùng tối đa (%):", "gpu_usage"),
            ("gpu_max_enc", "gpu_maximum_encoder_utilization_percent",
             "NVENC tối đa (%):", "gpu_nvenc"),
        )
        for attribute, field, label, tooltip_key in self._gpu_rows:
            default = d[field]
            widget = (
                dspin_for(field, float(default), tooltip_key)
                if field_limits.limit(field).decimals
                else spin_for(field, int(default), tooltip_key)
            )
            setattr(self, attribute, widget)
            form.addRow(label, widget)
        self.gpu_guidance = self._hint()
        self.gpu_guidance.setToolTip(tooltip("gpu_hardware"))
        form.addRow(self.gpu_guidance)
        restore = QPushButton("Khôi phục ngưỡng mặc định")
        restore.setToolTip(tooltip("gpu_reset"))
        restore.clicked.connect(self._restore_gpu_defaults)
        form.addRow(restore)
        self._connect_all(*(getattr(self, attribute) for attribute, *_rest in self._gpu_rows))

    # --- Wiring helpers -----------------------------------------------------

    @staticmethod
    def _hint() -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setObjectName("hint")
        return label

    def _connect_all(self, *widgets) -> None:
        for widget in widgets:
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(self._emit_changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._emit_changed)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self._emit_changed)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._emit_changed)

    def _emit_changed(self, *_args) -> None:
        if not self._loading:
            self.settings_changed.emit()

    # --- Model-driven reconfiguration --------------------------------------

    def current_model_id(self) -> str:
        return str(self.model_combo.currentData() or DEFAULT_GENERATION_PREFERENCES["model_id"])

    def _current_provider_id(self) -> str:
        return str(self.provider_combo.currentData() or model_groups.ALL_PROVIDERS)

    def _on_provider_changed(self, *_args) -> None:
        """Narrow the model list to the chosen provider, keeping a valid model."""
        was_loading = self._loading
        self._loading = True
        try:
            previous = self.model_combo.currentData()
            self.model_combo.clear()
            for label, model_id in self.ctrl.model_choices(self._current_provider_id()):
                self.model_combo.addItem(label, model_id)
            index = self.model_combo.findData(previous)
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._loading = was_loading
        if not self._loading:
            self.apply_model(self.current_model_id())
            self._emit_changed()

    def _select_model(self, model_id: str | None) -> None:
        if not model_id:
            return
        provider_id = self.ctrl.provider_of_model(model_id)
        index = self.provider_combo.findData(provider_id)
        if index >= 0 and index != self.provider_combo.currentIndex():
            self.provider_combo.setCurrentIndex(index)
        self._on_provider_changed()
        model_index = self.model_combo.findData(model_id)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

    def _on_model_changed(self, *_args) -> None:
        if self._loading:
            return
        self.apply_model(self.current_model_id())
        self._emit_changed()

    def apply_model(self, model_id: str, *, seed_defaults: bool | None = None) -> None:
        """Re-read the model contract. Provider defaults are re-seeded only when
        the model itself changed — otherwise switching voice mode would silently
        wipe tuning values the user is in the middle of typing."""
        was_loading = self._loading
        self._loading = True
        try:
            if seed_defaults is None:
                seed_defaults = model_id != self._seeded_model_id
            self.model_info.setText(self.ctrl.model_choice_info(model_id))
            self.runtime_status.setText(self.ctrl.runtime_status_text(model_id))
            self._policy = self.ctrl.control_policy(model_id)
            self._apply_policy(self._policy, seed_defaults=seed_defaults)
            if seed_defaults:
                self._seeded_model_id = model_id
            preferred = "fixed" if self.mode_fixed.isChecked() else "profile"
            self._apply_descriptor(
                self.ctrl.generation_form_descriptor(model_id, preferred), model_id
            )
            self.gpu_guidance.setText(self.ctrl.gpu_temperature_guidance())
        finally:
            self._loading = was_loading

    def _apply_policy(self, policy: GenerationControlPolicy, *, seed_defaults: bool) -> None:
        """Enable/disable every control according to what the model supports."""
        self._reload_combo(self.language_combo, policy.languages,
                           policy.default_language(self.language_combo.currentData()))
        self._reload_combo(self.device_combo, policy.device_targets,
                           policy.default_device(self.device_combo.currentData()))
        self.device_note.setText(policy.device_note)
        self.device_note.setVisible(bool(policy.device_note))

        self._apply_control(self.speed, policy.speed, NEUTRAL_SPEED)
        self._basic_form.setRowVisible(self._speed_row, policy.speed.supported)
        self._apply_control(self.pitch, policy.pitch, NEUTRAL_PITCH)
        self._basic_form.setRowVisible(self._pitch_row, policy.pitch.supported)
        self.punctuation_section.set_title(
            f"Ngắt nghỉ theo dấu câu · {policy.provider_label}"
        )
        self.punctuation_section.setVisible(policy.punctuation_pauses.supported)

        # Provider tuning: show the section only when something applies.
        emotions = [(value, value) for value in policy.emotions] or [("Tự nhiên", NEUTRAL_EMOTION)]
        self._reload_combo(self.vieneu_group.emotion_combo, emotions, policy.emotions[0]
                           if policy.emotions else NEUTRAL_EMOTION)
        self.vieneu_group.set_row_visible("codec", policy.codec.supported)
        self.vieneu_group.set_row_visible("sampling_temp", policy.sampling.supported)
        self.vieneu_group.set_row_visible("sampling_topk", policy.sampling.supported)
        self.vieneu_group.set_row_visible("emotion", policy.emotion.supported)
        groups = policy.tuning_groups
        for group, group_id in (
            (self.vieneu_group, control_policy.TUNING_VIENEU),
            (self.f5_group, control_policy.TUNING_F5),
            (self.chatterbox_group, control_policy.TUNING_CHATTERBOX),
            (self.higgs_remote_group, control_policy.TUNING_HIGGS_REMOTE),
        ):
            group.setVisible(group_id in groups)
        self.tuning_section.set_title(policy.tuning_title)
        self.tuning_section.setVisible(policy.has_tuning)
        if self.tuning_section.activation is not None:
            self.tuning_section.activation.setVisible(not policy.higgs_remote.supported)
        if policy.higgs_remote.supported:
            # Endpoint/transport fields are required connection settings, not
            # optional sound tuning, so this provider cannot deactivate them.
            self.tuning_section.set_active(True)
        self._sync_custom_voice_feature()
        self.tuning_absent.setText("" if policy.has_tuning else policy.tuning_absent_note())
        self.tuning_absent.setVisible(not policy.has_tuning)

        self.gpu_scope.setText(policy.gpu_scope_note)
        self.gpu_scope.setVisible(bool(policy.gpu_scope_note))

        if policy.codec.supported:
            self._populate_codecs(policy.model_id, keep_current=not seed_defaults)
        if not seed_defaults:
            return
        if policy.sampling.supported:
            self.vieneu_group.temperature.setValue(
                float(self.ctrl.default_vieneu_temperature(policy.model_id))
            )
            self.vieneu_group.top_k.setValue(int(self.ctrl.default_vieneu_top_k(policy.model_id)))
        if policy.f5.supported:
            self._seed_f5(self.ctrl.default_f5_settings(policy.model_id))
        if policy.chatterbox.supported:
            self._seed_chatterbox(self.ctrl.default_chatterbox_settings(policy.model_id))

    @staticmethod
    def _apply_control(widget, state, neutral) -> None:
        widget.setEnabled(state.supported)
        widget.setToolTip(state.tooltip)
        if not state.supported:
            widget.setValue(neutral)

    @staticmethod
    def _reload_combo(combo: QComboBox, choices, selected) -> None:
        combo.clear()
        for label, value in choices:
            combo.addItem(label, value)
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _apply_descriptor(self, descriptor, model_id: str) -> None:
        self._voice_form.setRowVisible(self._mode_row, descriptor.show_voice_mode_selector)
        if descriptor.selected_voice_mode == "profile":
            self.mode_profile.setChecked(True)
        else:
            self.mode_fixed.setChecked(True)
        self.fixed_voice_combo.clear()
        for option in descriptor.fixed_voices:
            self.fixed_voice_combo.addItem(option.label, option.voice_id)
        if descriptor.default_fixed_voice_id:
            index = self.fixed_voice_combo.findData(descriptor.default_fixed_voice_id)
            if index >= 0:
                self.fixed_voice_combo.setCurrentIndex(index)
        if self._policy and self._policy.higgs_remote:
            self._append_higgs_endpoint_voices(
                self.higgs_remote_group.voice.text().strip() or "default"
            )
        show_fixed = descriptor.show_fixed_voice and self.fixed_voice_combo.count() > 0
        self._voice_form.setRowVisible(self._fixed_row, show_fixed)
        self.profile_combo.clear()
        for name, pid in self.ctrl.voice_profile_choices():
            self.profile_combo.addItem(name, pid)
        self._voice_form.setRowVisible(self._profile_row, descriptor.show_profile)
        self._voice_form.setRowVisible(self._compat_row, descriptor.show_profile)
        self.voice_status.setText(descriptor.status_text)
        self._update_profile_compat(model_id)

    def _populate_codecs(self, model_id: str, *, keep_current: bool = False) -> None:
        combo = self.vieneu_group.codec_combo
        previous = combo.currentData() if keep_current else None
        combo.clear()
        for label, repo in self.ctrl.vieneu_codec_choices(model_id):
            combo.addItem(label, repo)
        wanted = previous or self.ctrl.default_vieneu_codec_repo(model_id)
        if wanted:
            index = combo.findData(wanted)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _seed_f5(self, defaults: dict) -> None:
        group = self.f5_group
        for key, widget in (
            ("f5_nfe_step", group.nfe), ("f5_cfg_strength", group.cfg),
            ("f5_sway_sampling_coef", group.sway), ("f5_cross_fade_duration", group.crossfade),
            ("f5_target_rms", group.rms),
        ):
            if defaults.get(key) is not None:
                widget.setValue(defaults[key])
        group.fix_duration.setValue(defaults.get("f5_fix_duration") or 0.0)
        seed = defaults.get("f5_seed")
        group.seed.setValue(seed if seed is not None else -1)
        group.remove_silence.setChecked(bool(defaults.get("f5_remove_silence")))

    def _seed_chatterbox(self, defaults: dict) -> None:
        group = self.chatterbox_group
        for key, widget in (
            ("chatterbox_temperature", group.temperature), ("chatterbox_top_p", group.top_p),
            ("chatterbox_top_k", group.top_k), ("chatterbox_repetition_penalty", group.repetition),
        ):
            if defaults.get(key) is not None:
                widget.setValue(defaults[key])
        seed = defaults.get("chatterbox_seed")
        group.seed.setValue(seed if seed is not None else -1)
        group.norm_loudness.setChecked(bool(defaults.get("chatterbox_norm_loudness", True)))

    def _check_higgs_endpoint(self) -> None:
        group = self.higgs_remote_group
        group.set_checking(True, "Đang kiểm tra /health và /v1/models…")
        settings = self.current_settings()
        task = FunctionTask(lambda: self.ctrl.check_higgs_endpoint(settings))
        task.signals.completed.connect(
            lambda result: group.set_checking(False, result.message)
        )
        task.signals.failed.connect(
            lambda message: group.set_checking(False, f"Lỗi: {message}")
        )
        # Keep a reference until Qt completes the runnable/signals.
        self._higgs_check_task = task
        QThreadPool.globalInstance().start(task)

    def _on_higgs_endpoint_type_changed(self, *_args) -> None:
        if self._loading:
            return
        self._sync_custom_voice_feature()
        self.apply_model(self.current_model_id(), seed_defaults=False)
        self._emit_changed()

    def _higgs_endpoint_settings(self) -> GenerationSettings:
        group = self.higgs_remote_group
        return GenerationSettings(
            model_id=self.current_model_id(),
            remote_endpoint_id=group.endpoint_id.text().strip()
            or "higgs-default",
            remote_api_flavor=str(group.api_flavor.currentData() or "sglang"),
            remote_base_url=group.endpoint_url.text().strip(),
            remote_auth_mode=str(group.auth_mode.currentData() or "none"),
            remote_auth_env=group.auth_env.text().strip()
            or "OMNI_TTS_REMOTE_API_KEY",
            remote_connect_timeout_seconds=group.connect_timeout.value(),
            remote_request_timeout_seconds=group.request_timeout.value(),
            remote_max_retries=group.retries.value(),
        )

    def _sync_custom_voice_feature(self) -> None:
        supported = bool(
            self._policy
            and self._policy.higgs_remote
            and self.ctrl.higgs_endpoint_capabilities(
                self._higgs_endpoint_settings()
            ).supports_custom_voice_create
        )
        self._voice_form.setRowVisible(self._custom_voice_row, supported)

    def _append_higgs_endpoint_voices(self, selected: str | None = None) -> None:
        existing = {
            str(self.fixed_voice_combo.itemData(index))
            for index in range(self.fixed_voice_combo.count())
        }
        for label, voice_id in self.ctrl.higgs_custom_voice_choices(
            self._higgs_endpoint_settings()
        ):
            if voice_id not in existing:
                self.fixed_voice_combo.addItem(label, voice_id)
                existing.add(voice_id)
        if selected:
            index = self.fixed_voice_combo.findData(selected)
            if index >= 0:
                self.fixed_voice_combo.setCurrentIndex(index)

    def _select_created_custom_voice(self, voice) -> None:
        self.apply_model(self.current_model_id(), seed_defaults=False)
        index = self.fixed_voice_combo.findData(voice.voice_id)
        if index >= 0:
            self.fixed_voice_combo.setCurrentIndex(index)
            self.mode_fixed.setChecked(True)

    def _on_voice_mode_changed(self, *_args) -> None:
        if self._loading:
            return
        self.apply_model(self.current_model_id())
        self._emit_changed()

    def _on_profile_changed(self, *_args) -> None:
        self._update_profile_compat(self.current_model_id())
        self._emit_changed()

    def _on_fixed_voice_changed(self, *_args) -> None:
        if self._loading:
            return
        if (
            self._policy
            and self._policy.higgs_remote
            and self.fixed_voice_combo.currentData()
        ):
            self.higgs_remote_group.voice.setText(
                str(self.fixed_voice_combo.currentData())
            )
        self._emit_changed()

    def _update_profile_compat(self, model_id: str) -> None:
        profile_id = self.profile_combo.currentData()
        if not profile_id or not self.mode_profile.isChecked():
            self.profile_compat.setText("")
            return
        try:
            compat = self.ctrl.profile_quality_for_model(str(profile_id), model_id)
        except Exception:
            self.profile_compat.setText("")
            return
        color = _STATUS_COLORS.get(compat.status, "#a1a1b3")
        self.profile_compat.setText(f'<span style="color:{color}">{compat.message}</span>')

    def _on_format_changed(self, *_args) -> None:
        self.bitrate_combo.setEnabled(self.format_combo.currentData() == "mp3")
        self._emit_changed()

    def _on_split_changed(self, *_args) -> None:
        self.join_split.setEnabled(self.split_output.isChecked())
        self._emit_changed()

    def _restore_gpu_defaults(self) -> None:
        self.gpu_section.set_active(True)
        for attribute, field, _label, _tooltip in self._gpu_rows:
            self._set_number(getattr(self, attribute), field, DEFAULT_GENERATION_PREFERENCES)

    def _restore_pause_defaults(self) -> None:
        self._apply_pause_values(DEFAULT_GENERATION_PREFERENCES)
        self.pause_preset_combo.setCurrentIndex(0)

    def _pause_values(self) -> dict[str, int | bool]:
        paragraph = PARAGRAPH_PAUSE_FIELD
        paragraph_fixed, paragraph_random, paragraph_min, paragraph_max = (
            self.paragraph_pause_editor.pause_values()
        )
        values: dict[str, int | bool] = {
            "punctuation_pause_enabled": self.punctuation_section.is_active(),
            "chunk_pause_ms": self.chunk_pause.milliseconds(),
            paragraph.fixed_field: paragraph_fixed,
            paragraph.random_field: paragraph_random,
            paragraph.minimum_field: paragraph_min,
            paragraph.maximum_field: paragraph_max,
        }
        for spec in PUNCTUATION_PAUSE_FIELDS:
            fixed, random_enabled, minimum, maximum = self.pause_editors[
                spec.key
            ].pause_values()
            values.update(
                {
                    spec.fixed_field: fixed,
                    spec.random_field: random_enabled,
                    spec.minimum_field: minimum,
                    spec.maximum_field: maximum,
                }
            )
        return values

    def _apply_pause_values(self, data: dict) -> None:
        self.punctuation_section.set_active(
            bool(data.get("punctuation_pause_enabled", True))
        )
        for spec in PUNCTUATION_PAUSE_FIELDS:
            editor = self.pause_editors[spec.key]
            editor.set_pause_values(
                int(
                    data.get(
                        spec.fixed_field,
                        DEFAULT_GENERATION_PREFERENCES[spec.fixed_field],
                    )
                ),
                bool(
                    data.get(
                        spec.random_field,
                        DEFAULT_GENERATION_PREFERENCES[spec.random_field],
                    )
                ),
                int(
                    data.get(
                        spec.minimum_field,
                        DEFAULT_GENERATION_PREFERENCES[spec.minimum_field],
                    )
                ),
                int(
                    data.get(
                        spec.maximum_field,
                        DEFAULT_GENERATION_PREFERENCES[spec.maximum_field],
                    )
                ),
            )
        self._set_pause(self.chunk_pause, "chunk_pause_ms", data)
        paragraph = PARAGRAPH_PAUSE_FIELD
        self.paragraph_pause_editor.set_pause_values(
            int(
                data.get(
                    paragraph.fixed_field,
                    DEFAULT_GENERATION_PREFERENCES[paragraph.fixed_field],
                )
            ),
            bool(
                data.get(
                    paragraph.random_field,
                    DEFAULT_GENERATION_PREFERENCES[paragraph.random_field],
                )
            ),
            int(
                data.get(
                    paragraph.minimum_field,
                    DEFAULT_GENERATION_PREFERENCES[paragraph.minimum_field],
                )
            ),
            int(
                data.get(
                    paragraph.maximum_field,
                    DEFAULT_GENERATION_PREFERENCES[paragraph.maximum_field],
                )
            ),
        )
        self._refresh_pause_tooltips()

    def _refresh_pause_tooltips(self, *_args) -> None:
        if not hasattr(self, "pause_editors"):
            return
        explanation = build_pause_explanation(self._pause_values())
        self.punctuation_section.setToolTip(explanation.section)
        if self.punctuation_section.activation is not None:
            self.punctuation_section.activation.setToolTip(explanation.section)
        self.punctuation_note.setToolTip(explanation.section)
        for spec in PUNCTUATION_PAUSE_FIELDS:
            detail = getattr(explanation, spec.key)
            self.pause_editors[spec.key].set_explanation_tooltip(
                f"{tooltip(spec.tooltip_key)}\n\n{detail}"
            )
        self.chunk_pause.setToolTip(
            f'{tooltip("chunk_pause")}\n\n{explanation.chunk}'
        )
        self.paragraph_pause_editor.set_explanation_tooltip(
            f'{tooltip("paragraph_pause")}\n\n{explanation.paragraph}'
        )

    def _refresh_pause_presets(self, selected_name: str | None = None) -> None:
        self.pause_preset_combo.blockSignals(True)
        self.pause_preset_combo.clear()
        self.pause_preset_combo.addItem("— Chọn preset —", None)
        for preset in self.ctrl.punctuation_pause_presets():
            self.pause_preset_combo.addItem(preset.name, preset.name)
        if selected_name:
            index = self.pause_preset_combo.findData(selected_name)
            if index >= 0:
                self.pause_preset_combo.setCurrentIndex(index)
        self.pause_preset_combo.blockSignals(False)
        self.pause_preset_delete.setEnabled(
            self.pause_preset_combo.currentData() is not None
        )

    def _apply_selected_pause_preset(self, *_args) -> None:
        name = self.pause_preset_combo.currentData()
        self.pause_preset_delete.setEnabled(name is not None)
        if not name:
            return
        preset = next(
            (
                item
                for item in self.ctrl.punctuation_pause_presets()
                if item.name == name
            ),
            None,
        )
        if preset is None:
            return
        self._apply_pause_values(preset.values)
        self._emit_changed()

    def _save_pause_preset(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "Lưu preset ngắt nghỉ", "Tên preset:"
        )
        if not accepted:
            return
        current_values = self._pause_values()
        try:
            preset = self.ctrl.save_punctuation_pause_preset(
                name, {key: current_values[key] for key in PAUSE_PRESET_KEYS}
            )
        except Exception as error:
            QMessageBox.warning(self, "Không lưu được preset", str(error))
            return
        self._refresh_pause_presets(preset.name)

    def _delete_pause_preset(self) -> None:
        name = self.pause_preset_combo.currentData()
        if not name:
            return
        if (
            QMessageBox.question(
                self, "Xóa preset", f'Xóa preset "{name}"?'
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.ctrl.delete_punctuation_pause_preset(str(name))
        except Exception as error:
            QMessageBox.warning(self, "Không xóa được preset", str(error))
            return
        self._refresh_pause_presets()

    # --- Sidebar voice selection hooks -------------------------------------

    def set_fixed_voice(self, voice_id: str) -> None:
        self.mode_fixed.setChecked(True)
        index = self.fixed_voice_combo.findData(voice_id)
        if index >= 0:
            self.fixed_voice_combo.setCurrentIndex(index)

    def set_profile(self, profile_id: str) -> None:
        self.mode_profile.setChecked(True)
        index = self.profile_combo.findData(profile_id)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)

    # --- Settings snapshot --------------------------------------------------

    def current_settings(self) -> GenerationSettings:
        policy = self._policy
        tuning = self.tuning_section.is_active()
        mode = "fixed" if self.mode_fixed.isChecked() else "profile"
        vieneu, f5, cb = self.vieneu_group, self.f5_group, self.chatterbox_group
        higgs = self.higgs_remote_group

        def on(state) -> bool:
            """A tuning control counts only if supported AND tuning is active."""
            return bool(policy is not None and state and tuning)

        sampling_on = on(policy.sampling) if policy else False
        emotion_on = on(policy.emotion) if policy else False
        codec_on = on(policy.codec) if policy else False
        f5_on = on(policy.f5) if policy else False
        cb_on = on(policy.chatterbox) if policy else False
        f5_seed = f5.seed.value()
        cb_seed = cb.seed.value()
        pause_values = self._pause_values()
        return GenerationSettings(
            language=str(self.language_combo.currentData() or "vi"),
            model_id=self.current_model_id(),
            voice_source_mode=mode,
            voice_profile_id=str(self.profile_combo.currentData())
            if mode == "profile" and self.profile_combo.currentData() else None,
            speaker_id=str(self.fixed_voice_combo.currentData())
            if mode == "fixed" and self.fixed_voice_combo.currentData() else None,
            speed=self.speed.value() if (policy is None or policy.speed) else NEUTRAL_SPEED,
            pitch_shift=self.pitch.value() if (policy is None or policy.pitch) else NEUTRAL_PITCH,
            emotion=str(vieneu.emotion_combo.currentData()) if emotion_on else NEUTRAL_EMOTION,
            runtime_target=str(self.device_combo.currentData() or "auto"),
            codec_repo=str(vieneu.codec_combo.currentData())
            if codec_on and vieneu.codec_combo.currentData() else None,
            temperature=vieneu.temperature.value() if sampling_on else None,
            top_k=vieneu.top_k.value() if sampling_on else None,
            f5_nfe_step=f5.nfe.value() if f5_on else None,
            f5_cfg_strength=f5.cfg.value() if f5_on else None,
            f5_sway_sampling_coef=f5.sway.value() if f5_on else None,
            f5_cross_fade_duration=f5.crossfade.value() if f5_on else None,
            f5_target_rms=f5.rms.value() if f5_on else None,
            f5_remove_silence=f5.remove_silence.isChecked() if f5_on else False,
            f5_seed=(f5_seed if f5_seed >= 0 else None) if f5_on else None,
            f5_fix_duration=(f5.fix_duration.value() or None) if f5_on else None,
            chatterbox_temperature=cb.temperature.value() if cb_on else None,
            chatterbox_top_p=cb.top_p.value() if cb_on else None,
            chatterbox_top_k=cb.top_k.value() if cb_on else None,
            chatterbox_repetition_penalty=cb.repetition.value() if cb_on else None,
            chatterbox_seed=(cb_seed if cb_seed >= 0 else None) if cb_on else None,
            chatterbox_norm_loudness=cb.norm_loudness.isChecked() if cb_on else True,
            gpu_safety_enabled=self.gpu_section.is_active(),
            gpu_start_temperature_c=self.gpu_start.value(),
            gpu_abort_temperature_c=self.gpu_abort.value(),
            gpu_abort_temperature_sustain_seconds=self.gpu_sustain.value(),
            gpu_emergency_temperature_c=self.gpu_emergency.value(),
            gpu_cooldown_max_wait_seconds=float(self.gpu_cooldown.value()),
            gpu_resume_temperature_c=self.gpu_resume.value(),
            gpu_minimum_free_vram_mb=self.gpu_min_vram.value(),
            gpu_runtime_minimum_free_vram_mb=self.gpu_runtime_vram.value(),
            gpu_maximum_utilization_percent=self.gpu_max_util.value(),
            gpu_maximum_encoder_utilization_percent=self.gpu_max_enc.value(),
            # Preserve the user's Piper choice while another provider is
            # selected. Core still gates the feature by provider capability.
            punctuation_pause_enabled=bool(pause_values["punctuation_pause_enabled"]),
            sentence_pause_ms=int(pause_values["sentence_pause_ms"]),
            sentence_pause_random_enabled=bool(
                pause_values["sentence_pause_random_enabled"]
            ),
            sentence_pause_min_ms=int(pause_values["sentence_pause_min_ms"]),
            sentence_pause_max_ms=int(pause_values["sentence_pause_max_ms"]),
            comma_pause_ms=int(pause_values["comma_pause_ms"]),
            comma_pause_random_enabled=bool(
                pause_values["comma_pause_random_enabled"]
            ),
            comma_pause_min_ms=int(pause_values["comma_pause_min_ms"]),
            comma_pause_max_ms=int(pause_values["comma_pause_max_ms"]),
            clause_pause_ms=int(pause_values["clause_pause_ms"]),
            clause_pause_random_enabled=bool(
                pause_values["clause_pause_random_enabled"]
            ),
            clause_pause_min_ms=int(pause_values["clause_pause_min_ms"]),
            clause_pause_max_ms=int(pause_values["clause_pause_max_ms"]),
            ellipsis_pause_ms=int(pause_values["ellipsis_pause_ms"]),
            ellipsis_pause_random_enabled=bool(
                pause_values["ellipsis_pause_random_enabled"]
            ),
            ellipsis_pause_min_ms=int(pause_values["ellipsis_pause_min_ms"]),
            ellipsis_pause_max_ms=int(pause_values["ellipsis_pause_max_ms"]),
            chunk_pause_ms=self.chunk_pause.milliseconds(),
            paragraph_pause_ms=int(pause_values["paragraph_pause_ms"]),
            paragraph_pause_random_enabled=bool(
                pause_values["paragraph_pause_random_enabled"]
            ),
            paragraph_pause_min_ms=int(pause_values["paragraph_pause_min_ms"]),
            paragraph_pause_max_ms=int(pause_values["paragraph_pause_max_ms"]),
            max_chunk_chars=self.max_chunk.value(),
            output_dir=self.output_path.value(),
            overwrite=self.overwrite.isChecked(),
            split_output=self.split_output.isChecked(),
            output_audio_format=str(self.format_combo.currentData()),
            mp3_bitrate_kbps=int(self.bitrate_combo.currentData()),
            output_srt=self.output_srt.isChecked(),
            join_split_output_audio=self.join_split.isChecked(),
            # Preserve the endpoint profile while switching to a local model.
            # TtsService capability-gates it and only passes it to remote engines.
            remote_base_url=higgs.endpoint_url.text().strip(),
            remote_endpoint_id=higgs.endpoint_id.text().strip()
            or "higgs-default",
            remote_api_flavor=str(higgs.api_flavor.currentData() or "sglang"),
            remote_auth_mode=str(higgs.auth_mode.currentData() or "none"),
            remote_auth_env=higgs.auth_env.text().strip()
            or "OMNI_TTS_REMOTE_API_KEY",
            remote_connect_timeout_seconds=higgs.connect_timeout.value(),
            remote_request_timeout_seconds=higgs.request_timeout.value(),
            remote_max_retries=higgs.retries.value(),
            higgs_model=higgs.model.text().strip(),
            higgs_voice=(
                str(self.fixed_voice_combo.currentData() or "default")
                if policy and policy.higgs_remote and mode == "fixed"
                else higgs.voice.text().strip() or "default"
            ),
            higgs_stream=higgs.stream.isChecked(),
            higgs_response_format=str(higgs.response_format.currentData() or "pcm"),
            higgs_max_new_tokens=higgs.max_new_tokens.value(),
            higgs_temperature=higgs.temperature.value(),
            higgs_top_p=higgs.top_p.value() if higgs.top_p_enabled.isChecked() else None,
            higgs_top_k=higgs.top_k.value() if higgs.top_k_enabled.isChecked() else None,
            higgs_seed=higgs.seed.value() if higgs.seed.value() >= 0 else None,
            higgs_initial_codec_chunk_frames=higgs.codec_frames.value(),
            higgs_concurrency=higgs.concurrency.value(),
            higgs_emotion=str(higgs.emotion.currentData() or ""),
            higgs_style=str(higgs.style.currentData() or ""),
            higgs_speed=str(higgs.speed.currentData() or ""),
            higgs_pitch=str(higgs.pitch.currentData() or ""),
            higgs_expressiveness=str(higgs.expressiveness.currentData() or ""),
            higgs_delivery_tags=higgs.delivery_tags.text().strip(),
        )

    # --- Preferences round-trip --------------------------------------------

    def load_preferences(self, data: dict) -> None:
        self._loading = True
        try:
            self._select_model(data.get("model_id"))
            self.apply_model(self.current_model_id())
            # Only restore values the current model actually supports; the rest
            # stay at the neutral values apply_model just set.
            self._set_combo(self.language_combo, data.get("language"))
            self._set_combo(self.device_combo, data.get("runtime_target"))
            if self._policy is None or self._policy.speed:
                self.speed.setValue(float(data.get("speed", NEUTRAL_SPEED)))
            if self._policy is None or self._policy.pitch:
                self.pitch.setValue(float(data.get("pitch_shift", NEUTRAL_PITCH)))
            self._apply_pause_values(data)
            self.max_chunk.setValue(int(data.get("max_chunk_chars", 220)))
            self.output_path.set_value(data.get("output_dir") or "")
            self._set_combo(self.format_combo, data.get("output_audio_format", "wav"))
            self._set_combo(self.bitrate_combo, int(data.get("mp3_bitrate_kbps", 192)))
            self.overwrite.setChecked(bool(data.get("overwrite", False)))
            self.split_output.setChecked(bool(data.get("split_output", True)))
            self.output_srt.setChecked(bool(data.get("output_srt", False)))
            self.join_split.setChecked(bool(data.get("join_split_output_audio", False)))
            if data.get("voice_source_mode") == "profile":
                self.mode_profile.setChecked(True)
            self._set_combo(self.profile_combo, data.get("voice_profile_id"))
            self._set_combo(self.fixed_voice_combo, data.get("speaker_id"))
            self._load_tuning(data)
            # Endpoint settings belong to the Higgs provider profile and must
            # survive even when the app starts on a different provider.
            self._load_higgs_remote(data)
            self.gpu_section.set_active(bool(data.get("gpu_safety_enabled", True)))
            self._load_gpu(data)
            self.bitrate_combo.setEnabled(self.format_combo.currentData() == "mp3")
            self.join_split.setEnabled(self.split_output.isChecked())
        finally:
            self._loading = False

    def _load_tuning(self, data: dict) -> None:
        """Restore provider tuning, but only what the current model honours —
        a saved F5 seed must not leak into a Chatterbox run."""
        policy = self._policy
        if policy is None:
            return
        if policy.codec:
            self._set_combo(self.vieneu_group.codec_combo, data.get("codec_repo"))
        if policy.sampling:
            self._set_number(self.vieneu_group.temperature, "temperature", data)
            self._set_number(self.vieneu_group.top_k, "top_k", data)
        if policy.emotion:
            self._set_combo(self.vieneu_group.emotion_combo, data.get("emotion"))
        if policy.f5:
            for field, widget in (
                ("f5_nfe_step", self.f5_group.nfe),
                ("f5_cfg_strength", self.f5_group.cfg),
                ("f5_sway_sampling_coef", self.f5_group.sway),
                ("f5_cross_fade_duration", self.f5_group.crossfade),
                ("f5_target_rms", self.f5_group.rms),
                ("f5_fix_duration", self.f5_group.fix_duration),
                ("f5_seed", self.f5_group.seed),
            ):
                self._set_number(widget, field, data)
            self.f5_group.remove_silence.setChecked(bool(data.get("f5_remove_silence", False)))
        if policy.chatterbox:
            for field, widget in (
                ("chatterbox_temperature", self.chatterbox_group.temperature),
                ("chatterbox_top_p", self.chatterbox_group.top_p),
                ("chatterbox_top_k", self.chatterbox_group.top_k),
                ("chatterbox_repetition_penalty", self.chatterbox_group.repetition),
                ("chatterbox_seed", self.chatterbox_group.seed),
            ):
                self._set_number(widget, field, data)
            self.chatterbox_group.norm_loudness.setChecked(
                bool(data.get("chatterbox_norm_loudness", True))
            )
        # Values just restored belong to this model; do not overwrite them.
        self._seeded_model_id = self.current_model_id()

    def _load_higgs_remote(self, data: dict) -> None:
        group = self.higgs_remote_group
        group.endpoint_id.setText(
            str(data.get("remote_endpoint_id") or "higgs-default")
        )
        group.endpoint_url.setText(str(data.get("remote_base_url") or ""))
        self._set_combo(group.api_flavor, data.get("remote_api_flavor", "sglang"))
        self._set_combo(group.auth_mode, data.get("remote_auth_mode", "none"))
        group.auth_env.setText(
            str(data.get("remote_auth_env") or "OMNI_TTS_REMOTE_API_KEY")
        )
        group.model.setText(str(data.get("higgs_model") or ""))
        saved_voice = str(data.get("higgs_voice") or "default")
        group.voice.setText(saved_voice)
        if self._policy and self._policy.higgs_remote:
            self._append_higgs_endpoint_voices(saved_voice)
        group.stream.setChecked(bool(data.get("higgs_stream", True)))
        self._set_combo(group.response_format, data.get("higgs_response_format", "pcm"))
        for field, widget in (
            ("higgs_max_new_tokens", group.max_new_tokens),
            ("higgs_temperature", group.temperature),
            ("higgs_seed", group.seed),
            ("higgs_initial_codec_chunk_frames", group.codec_frames),
            ("higgs_concurrency", group.concurrency),
            ("remote_connect_timeout_seconds", group.connect_timeout),
            ("remote_request_timeout_seconds", group.request_timeout),
            ("remote_max_retries", group.retries),
        ):
            value = data.get(field)
            if value is not None:
                widget.setValue(value)
        top_p = data.get("higgs_top_p")
        group.top_p_enabled.setChecked(top_p is not None)
        if top_p is not None:
            group.top_p.setValue(float(top_p))
        top_k = data.get("higgs_top_k")
        group.top_k_enabled.setChecked(top_k is not None)
        if top_k is not None:
            group.top_k.setValue(int(top_k))
        self._set_combo(group.emotion, data.get("higgs_emotion", ""))
        self._set_combo(group.style, data.get("higgs_style", ""))
        self._set_combo(group.speed, data.get("higgs_speed", ""))
        self._set_combo(group.pitch, data.get("higgs_pitch", ""))
        self._set_combo(group.expressiveness, data.get("higgs_expressiveness", ""))
        group.delivery_tags.setText(str(data.get("higgs_delivery_tags") or ""))

    def _load_gpu(self, data: dict) -> None:
        for _attribute, field, _label, _tooltip in self._gpu_rows:
            self._set_number(getattr(self, _attribute), field, data)

    @staticmethod
    def _set_number(widget, field: str, data: dict) -> None:
        """Write a stored value into a spin box, clamped to what the core accepts."""
        value = data.get(field)
        limit = field_limits.limit(field)
        if value is None:
            if limit.sentinel is not None:
                widget.setValue(limit.sentinel)
            return
        clamped = limit.clamp(float(value))
        widget.setValue(int(clamped) if limit.is_integer else clamped)

    @staticmethod
    def _set_pause(widget, field: str, data: dict) -> None:
        """Restore a persisted millisecond value into a seconds-facing input."""
        value = data.get(field)
        if value is None:
            return
        clamped = field_limits.limit(field).clamp(float(value))
        widget.set_milliseconds(clamped)

    def save_preferences(self, data: dict) -> None:
        data.update(self.current_settings().to_preferences())

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
