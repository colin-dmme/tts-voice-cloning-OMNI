"""Studio section "Nhịp đọc": one pause setting set for every model.

The user's Min–Max values never change with the model. Each layer row carries
a badge resolved by Core (MODEL / APP / MODEL TỰ LO + APP BÙ / GIỚI HẠN /
KHÔNG ÁP DỤNG / TẮT) saying who realises that pause for the chosen model.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.chapter_music import ChapterMusicLibrary, music_theme_label
from omni_tts_core.rhythm.layers import LAYER_BY_ID, LAYER_GROUPS, LAYERS, layer_range
from omni_tts_core.rhythm.presets import apply_rhythm_preset
from omni_tts_core.ui_presenters.rhythm_presenter import (
    PRESET_CHOICES,
    SCOPE_CHOICES,
    RhythmView,
)
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.narrative_pacing import NarrativePacingOptions
from omni_tts_ui_qt.widgets.chapter_music import ChapterMusicWidget

_SELECTION_KEYS = (
    "selection_mode", "track_id", "preset_id", "theme", "random_seed",
    "theme_ids", "track_ids", "excluded_track_ids",
)
_RANGE_LAYERS = tuple(spec.layer for spec in LAYERS if spec.field)
_ROW_HINTS = {
    "connector": "Đoạn sau mở bằng Bởi vậy, Nhưng, Như vậy…",
    "question": "Đoạn trước kết bằng dấu hỏi",
    "emphasis": "Một trong hai đoạn là câu ngắn chốt ý",
    "subtopic": "Trước hết, Từ đây, Điểm thứ…",
    "section": "Chủ đề đổi rõ (tự nhận theo nội dung), không nhạc",
    "short_sentence": "Trước/sau câu ngắn ≤32 ký tự",
    "comma": "0 = giữ nguyên nhịp model",
}


def _seconds(minimum: float, maximum: float, step: float = 0.05, suffix: str = " giây") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(2)
    spin.setSuffix(suffix)
    return spin


def _badge() -> QLabel:
    label = QLabel()
    label.setMinimumWidth(96)
    return label


class NarrativePacingWidget(QWidget):
    changed = Signal()
    # The panel answers with the old punctuation/paragraph values.
    legacy_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._options = NarrativePacingOptions()
        self._loading = True
        self._view: RhythmView | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        intro = QLabel(
            "Một bộ khoảng nghỉ dùng chung cho mọi model, tính theo tổng khoảng lặng nghe thấy. "
            "Đổi model không đổi các con số; nhãn mỗi dòng cho biết model hay app làm khoảng nghỉ đó."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        head = QFormLayout()
        layout.addLayout(head)
        self.enabled = QCheckBox("Bật Nhịp đọc")
        self.scope = QComboBox()
        for label, value in SCOPE_CHOICES:
            self.scope.addItem(label, value)
        self.scope.setToolTip(
            "Chỉ nhịp kể chuyện: mục Ngắt nghỉ theo dấu câu vẫn chạy như cũ, Nhịp đọc chỉ giãn thêm.\n"
            "Toàn bộ ngắt nghỉ: Nhịp đọc chọn đúng một bên cho mỗi tầng và khóa các mục cũ trùng việc."
        )
        preset_row = QHBoxLayout()
        self.preset = QComboBox()
        for label, value in PRESET_CHOICES:
            self.preset.addItem(label, value)
        self.apply_preset = QPushButton("Áp dụng")
        self.from_legacy = QPushButton("Lấy từ cài đặt cũ")
        self.from_legacy.setToolTip(
            "Đề xuất khoảng nghỉ từ mục Ngắt nghỉ theo dấu câu và Nghỉ giữa đoạn gốc "
            "(cộng thêm khoảng lặng model tự nghỉ, vì Nhịp đọc tính tổng)."
        )
        preset_row.addWidget(self.preset, 1)
        preset_row.addWidget(self.apply_preset)
        preset_row.addWidget(self.from_legacy)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        head.addRow(self.enabled)
        head.addRow("Phạm vi", self.scope)
        head.addRow("Preset", preset_row)
        head.addRow(self.summary)

        self.switch_box = QGroupBox("Riêng cho model đang chọn")
        self.switch_form = QFormLayout(self.switch_box)
        self._switch_widgets: dict[str, QComboBox] = {}
        layout.addWidget(self.switch_box)
        self.switch_box.hide()

        self.sentences = QCheckBox("Xếp nhịp trong đoạn (dấu câu, câu ngắn)")
        self.sections = QCheckBox("Lặng dài khi chuyển mục (tự nhận theo nội dung)")
        self.section_interval = _seconds(1, 30, 0.5, " phút")
        layout.addWidget(self.sentences)
        grid = QGridLayout()
        layout.addLayout(grid)
        self._mins: dict[str, QDoubleSpinBox] = {}
        self._maxs: dict[str, QDoubleSpinBox] = {}
        self._badges: dict[str, QLabel] = {}
        self._labels: dict[str, QLabel] = {}
        row = 0
        current_group = None
        for spec in LAYERS:
            if not spec.field:
                continue
            if spec.group != current_group:
                current_group = spec.group
                if spec.group == "between_paragraphs":
                    grid.addWidget(self.sections, row, 0, 1, 5)
                    row += 1
                title = QLabel(f"<b>{LAYER_GROUPS[spec.group]}</b>")
                grid.addWidget(title, row, 0)
                grid.addWidget(QLabel("Min"), row, 1)
                grid.addWidget(QLabel("Max"), row, 2)
                row += 1
            label = QLabel(spec.label)
            label.setToolTip(_ROW_HINTS.get(spec.layer, ""))
            low, high = _seconds(0, 8), _seconds(0, 8)
            low.valueChanged.connect(lambda value, layer=spec.layer: self._on_min(layer, value))
            high.valueChanged.connect(lambda value, layer=spec.layer: self._on_max(layer, value))
            badge = _badge()
            grid.addWidget(label, row, 0)
            grid.addWidget(low, row, 1)
            grid.addWidget(high, row, 2)
            grid.addWidget(badge, row, 3)
            self._labels[spec.layer], self._mins[spec.layer] = label, low
            self._maxs[spec.layer], self._badges[spec.layer] = high, badge
            row += 1
        grid.addWidget(QLabel("Khoảng một mục mỗi"), row, 0)
        grid.addWidget(self.section_interval, row, 1, 1, 2)
        grid.setColumnStretch(0, 1)

        form = QFormLayout()
        layout.addLayout(form)
        self.music = QCheckBox("Chèn nhạc chuyển giao thoa giữa các phần lớn")
        self.music_badges = QLabel()
        self.music_badges.setWordWrap(True)
        self.source = ChapterMusicWidget(source_only=True)
        self.source.setTitle("Nhạc chuyển")
        for control in (self.source.volume,):
            control.hide()
            label = self.source._form.labelForField(control)
            if label:
                label.hide()
        self.interval = _seconds(2, 60, 1, " phút")
        self.level = _seconds(-30, 0, 0.5, " dB")
        self.overlap_in = _seconds(0, 4, 0.1)
        self.overlap_out = _seconds(0, 6, 0.1)
        self.theme_track = QComboBox()
        self.hook = _seconds(0, 300, 1)
        self.major = QCheckBox("Nhạc chuyển dài (~10s) ở các bước ngoặt lớn và lúc kết")
        self.major_interval = _seconds(5, 180, 5, " phút")
        self.major_solo = _seconds(1, 20, 0.5)
        self.major_source = QComboBox()
        form.addRow(self.music)
        form.addRow(self.music_badges)
        layout.addWidget(self.source)
        music_form = QFormLayout()
        layout.addLayout(music_form)
        music_form.addRow("Nhạc ngắn (~5s): khoảng mỗi", self.interval)
        music_form.addRow(self.major)
        music_form.addRow("Nhạc dài: khoảng mỗi", self.major_interval)
        music_form.addRow("Nhạc dài: phần chỉ có nhạc", self.major_solo)
        music_form.addRow("Nhạc dài: nguồn", self.major_source)
        music_form.addRow("Mức nhạc so với giọng", self.level)
        music_form.addRow("Nhạc vào trước khi giọng dứt", self.overlap_in)
        music_form.addRow("Nhạc còn sau khi giọng vào", self.overlap_out)
        music_form.addRow("Nhạc mở / kết series", self.theme_track)
        music_form.addRow("Hook đầu không nhạc, tối thiểu", self.hook)
        self.note = QLabel(
            "Hook đầu luôn để trơn; nhạc mở vào ở câu giới thiệu series (Đây là…, podcast, kênh…). "
            "Nhạc chuyển ưu tiên các mốc Trước hết / Bây giờ / Đến đây / Vậy nếu… "
            "Nhạc dài lấy một đoạn của nhạc mở / kết series (chữ ký của kênh). "
            "Với EPUB, chương/cảnh và nhạc chương do mục Đọc sách EPUB quản lý."
        )
        self.note.setWordWrap(True)
        music_form.addRow(self.note)
        self._music_controls = (self.source, self.interval, self.level, self.overlap_in,
                                self.overlap_out, self.theme_track, self.hook, self.major,
                                self.major_interval, self.major_solo, self.major_source)
        self._refresh_themes()
        for spin in (self.section_interval, self.major_interval, self.major_solo,
                     self.interval, self.level, self.overlap_in, self.overlap_out, self.hook):
            spin.valueChanged.connect(self._emit)
        for box in (self.enabled, self.sections, self.sentences, self.music, self.major):
            box.toggled.connect(self._emit)
        for combo in (self.theme_track, self.major_source, self.scope):
            combo.currentIndexChanged.connect(self._emit)
        self.source.changed.connect(self._emit)
        self.apply_preset.clicked.connect(self._apply_preset)
        self.from_legacy.clicked.connect(self.legacy_requested.emit)
        self.set_options({})
        self._loading = False

    # --- layer values ---------------------------------------------------

    def _on_min(self, layer: str, value: float) -> None:
        if self._maxs[layer].value() < value:
            self._maxs[layer].setValue(value)
        self._emit()

    def _on_max(self, layer: str, value: float) -> None:
        if self._mins[layer].value() > value:
            self._mins[layer].setValue(value)
        self._emit()

    def _apply_preset(self) -> None:
        options = apply_rhythm_preset(NarrativePacingOptions.model_validate(self.options()),
                                      str(self.preset.currentData()))
        self.set_options(options.model_dump())
        self._emit()

    def apply_ranges(self, ranges: dict[str, list[int]]) -> None:
        """Fill layer rows from a suggestion (e.g. the old pause settings)."""
        loading, self._loading = self._loading, True
        for layer, (low, high) in ranges.items():
            if layer in self._mins:
                self._mins[layer].setValue(low / 1000)
                self._maxs[layer].setValue(high / 1000)
        self._loading = loading
        self._emit()

    # --- model-dependent view -------------------------------------------

    def set_view(self, view: RhythmView | None) -> None:
        """Show who realises each layer for the chosen model (Core-resolved)."""
        self._view = view
        plan = view.plan if view else None
        enabled = bool(plan and plan.enabled)
        self.summary.setText(view.status_text if view else "")
        self.summary.setVisible(bool(view and view.status_text))
        for layer, badge in self._badges.items():
            row = view.row(layer) if view else None
            if row is None:
                badge.setText("")
                badge.setToolTip("")
                continue
            badge.setText(f'<span style="color:{row.color};font-weight:600">{row.state_label}</span>')
            badge.setToolTip(row.tooltip)
            self._labels[layer].setToolTip(f"{_ROW_HINTS.get(layer, '')}\n\n{row.tooltip}".strip())
        music_rows = [view.row(layer) for layer in ("music_theme", "music_short", "music_long")] if view else []
        self.music_badges.setText(" · ".join(
            f'{row.label}: <span style="color:{row.color}">{row.state_label}</span>'
            for row in music_rows if row
        ))
        self.music_badges.setToolTip("\n".join(row.tooltip for row in music_rows if row))
        self._rebuild_switches(view if enabled else None)
        self._sync_enabled()

    def _rebuild_switches(self, view: RhythmView | None) -> None:
        while self.switch_form.rowCount():
            self.switch_form.removeRow(0)
        self._switch_widgets.clear()
        switches = view.plan.switches if view else ()
        for state in switches:
            combo = QComboBox()
            for value, label in state.switch.choices:
                combo.addItem(label, value)
            combo.setCurrentIndex(max(0, combo.findData(state.value)))
            note = "" if state.active else " (chỉ dùng ở phạm vi Toàn bộ ngắt nghỉ)"
            combo.setToolTip(state.switch.help + note)
            combo.setEnabled(state.active)
            combo.currentIndexChanged.connect(self._emit)
            self._switch_widgets[state.switch.key] = combo
            self.switch_form.addRow(state.switch.label, combo)
        if view:
            self.switch_box.setTitle(f"Riêng cho {view.plan.model_label or view.plan.provider_label}")
        self.switch_box.setVisible(bool(switches))

    def _emit(self, *_):
        self._sync_enabled()
        if not self._loading:
            self.changed.emit()

    def _sync_enabled(self):
        on = self.enabled.isChecked()
        for control in (self.scope, self.preset, self.apply_preset, self.from_legacy,
                        self.sections, self.sentences, self.music, self.switch_box):
            control.setEnabled(on)
        for spec in LAYERS:
            if spec.layer not in self._mins:
                continue
            row = self._view.row(spec.layer) if self._view else None
            group_on = (self.sentences.isChecked() if spec.group in {"in_sentence", "sentence_end"}
                        else not (spec.layer == "section" and not self.sections.isChecked()))
            # A layer that does not apply keeps its value, greyed out.
            usable = on and group_on and (row is None or row.applies or row.state == "off")
            self._mins[spec.layer].setEnabled(usable)
            self._maxs[spec.layer].setEnabled(usable)
        self.section_interval.setEnabled(on and self.sections.isChecked())
        for control in self._music_controls:
            control.setEnabled(on and self.music.isChecked())
        for control in (self.major_interval, self.major_solo, self.major_source):
            control.setEnabled(on and self.music.isChecked() and self.major.isChecked())

    # --- music sources ----------------------------------------------------

    def _refresh_major_sources(self, tracks):
        current = self.major_source.currentData()
        self.major_source.clear()
        self.major_source.addItem("Đoạn trích nhạc mở / kết series", None)
        # Only groups made entirely of long tracks: a long bridge needs ~12 s of music.
        short_groups = {theme for t in tracks if t.duration_seconds < 12 for theme in t.themes}
        groups = sorted({theme for t in tracks for theme in t.themes} - short_groups - {"mo-ket"},
                        key=lambda g: (g != "chuyen-chuong", g))
        for group in groups:
            self.major_source.addItem(f"Nhóm: {music_theme_label(group)}", group)
        self.major_source.setCurrentIndex(max(0, self.major_source.findData(current)))

    def _refresh_themes(self):
        current = self.theme_track.currentData()
        self.theme_track.clear()
        self.theme_track.addItem("Không dùng nhạc mở / kết", None)
        try:
            tracks = ChapterMusicLibrary().list_tracks()
        except ConfigError:
            tracks = []
        self._refresh_major_sources(tracks)
        # Series themes first, then anything else long enough to carry an intro.
        ranked = sorted(tracks, key=lambda t: ("mo-ket" not in t.themes, t.name))
        for track in ranked:
            if "mo-ket" in track.themes or track.duration_seconds >= 10:
                self.theme_track.addItem(f"{track.name} ({track.duration_seconds:.0f}s)", track.track_id)
        index = self.theme_track.findData(current)
        self.theme_track.setCurrentIndex(max(0, index))

    # --- (de)serialisation ------------------------------------------------

    def _layer_values(self) -> dict:
        """Single *_pause_ms fields plus layer_ranges for rows with Min < Max."""
        values: dict = {}
        ranges: dict[str, list[int]] = {}
        sentence_low = round(self._mins["sentence_end"].value() * 1000)
        for layer in _RANGE_LAYERS:
            spec = LAYER_BY_ID[layer]
            low = round(self._mins[layer].value() * 1000)
            high = round(self._maxs[layer].value() * 1000)
            if layer == "ellipsis":
                # No field of its own: it follows the sentence pause unless edited.
                if (low, high) != (sentence_low + spec.offset_ms,) * 2:
                    ranges[layer] = [low, high]
                continue
            values[spec.field] = low
            if high != low:
                ranges[layer] = [low, high]
        values["layer_ranges"] = ranges
        return values

    def options(self) -> dict:
        source = self.source.options()
        music = self._options.music.model_copy(update={
            **{key: source[key] for key in _SELECTION_KEYS},
            "enabled": self.music.isChecked(),
            "interval_minutes": self.interval.value(),
            "level_db": self.level.value(),
            "overlap_in_ms": int(self.overlap_in.value() * 1000),
            "overlap_out_ms": int(self.overlap_out.value() * 1000),
            "theme_track_id": self.theme_track.currentData(),
            "hook_min_seconds": self.hook.value(),
            "major_enabled": self.major.isChecked(),
            "major_interval_minutes": self.major_interval.value(),
            "major_solo_ms": int(self.major_solo.value() * 1000),
            "major_theme": self.major_source.currentData(),
        })
        switches = dict(self._options.model_switches)
        switches.update({key: str(combo.currentData()) for key, combo in self._switch_widgets.items()})
        return self._options.model_copy(update={
            "enabled": self.enabled.isChecked(),
            "scope": self.scope.currentData() or "pacing_only",
            "model_switches": switches,
            **self._layer_values(),
            "sections_enabled": self.sections.isChecked(),
            "section_interval_minutes": self.section_interval.value(),
            "sentence_pauses_enabled": self.sentences.isChecked(),
            "music": music,
        }).model_dump()

    def set_options(self, data) -> None:
        try:
            options = NarrativePacingOptions.model_validate(data or {})
        except ValueError:
            options = NarrativePacingOptions()
        loading, self._loading = self._loading, True
        self._options = options
        self.enabled.setChecked(options.enabled)
        self.scope.setCurrentIndex(max(0, self.scope.findData(options.scope)))
        for layer in _RANGE_LAYERS:
            low, high = layer_range(options, layer) or (0, 0)
            self._mins[layer].setValue(low / 1000)
            self._maxs[layer].setValue(high / 1000)
        self.sections.setChecked(options.sections_enabled)
        self.section_interval.setValue(options.section_interval_minutes)
        self.sentences.setChecked(options.sentence_pauses_enabled)
        for key, combo in self._switch_widgets.items():
            if key in options.model_switches:
                combo.setCurrentIndex(max(0, combo.findData(options.model_switches[key])))
        music = options.music
        self.music.setChecked(music.enabled)
        self.source.set_options({key: getattr(music, key) for key in _SELECTION_KEYS})
        self.interval.setValue(music.interval_minutes)
        self.level.setValue(music.level_db)
        self.overlap_in.setValue(music.overlap_in_ms / 1000)
        self.overlap_out.setValue(music.overlap_out_ms / 1000)
        self.hook.setValue(music.hook_min_seconds)
        self.major.setChecked(music.major_enabled)
        self.major_interval.setValue(music.major_interval_minutes)
        self.major_solo.setValue(music.major_solo_ms / 1000)
        index = self.major_source.findData(music.major_theme)
        if music.major_theme and index < 0:
            self.major_source.addItem(f"Nhóm {music.major_theme} (không còn nhạc)", music.major_theme)
            index = self.major_source.count() - 1
        self.major_source.setCurrentIndex(max(0, index))
        self._refresh_themes()
        if music.theme_track_id and self.theme_track.findData(music.theme_track_id) < 0:
            self.theme_track.addItem("Nhạc đã lưu không còn — hãy chọn lại", music.theme_track_id)
        self.theme_track.setCurrentIndex(max(0, self.theme_track.findData(music.theme_track_id)))
        self._sync_enabled()
        self._loading = loading
