"""Provider-specific tuning groups (VieNeu / F5-TTS / Chatterbox).

Each group is a plain widget with a form; the settings panel shows only the
groups the selected model actually supports (`policy.tuning_groups`) and hides
the individual rows the model cannot honour (e.g. VieNeu v3 Turbo has no emotion
presets).

Ranges come from `field_limits` (i.e. from the request schema) and help text from
`tooltips`, so a knob here can never offer a value the core rejects and never
explains itself differently from the tkinter GUI.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from omni_tts_core.provider_options import ProviderSettingSpec
from omni_tts_core.ui_presenters.tooltips import tooltip
from omni_tts_ui_qt.widgets.common import dspin_for, make_combo, spin_for

EMOTION_FALLBACK = [("Tự nhiên", "natural")]


class _Group(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._rows: dict[str, int] = {}

    def add(self, key: str, label: str, widget: QWidget, tooltip_key: str = "") -> QWidget:
        if tooltip_key:
            widget.setToolTip(tooltip(tooltip_key))
        self._rows[key] = self.form.rowCount()
        self.form.addRow(label, widget)
        return widget

    def set_row_visible(self, key: str, visible: bool) -> None:
        row = self._rows.get(key)
        if row is not None:
            self.form.setRowVisible(row, visible)

    def widgets(self) -> list[QWidget]:
        return [self.form.itemAt(row, QFormLayout.ItemRole.FieldRole).widget()
                for row in range(self.form.rowCount())
                if self.form.itemAt(row, QFormLayout.ItemRole.FieldRole) is not None]


class DeclarativeProviderGroup(_Group):
    """Draw any provider option from Core metadata; contains no provider names."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._settings: tuple[ProviderSettingSpec, ...] = ()
        self._widgets: dict[str, QWidget] = {}

    def configure(
        self,
        settings: tuple[ProviderSettingSpec, ...],
        values: dict | None = None,
    ) -> None:
        self._clear()
        self._settings = tuple(settings)
        supplied = dict(values or {})
        for setting in self._settings:
            value = supplied.get(setting.key, setting.default)
            if setting.kind == "boolean":
                widget = QCheckBox()
                widget.setChecked(bool(value))
                widget.toggled.connect(self.changed.emit)
            elif setting.kind == "integer":
                widget = QSpinBox()
                widget.setRange(int(setting.minimum or 0), int(setting.maximum or 999999))
                widget.setSingleStep(max(1, int(setting.step or 1)))
                widget.setValue(int(value))
                widget.valueChanged.connect(self.changed.emit)
            elif setting.kind == "number":
                widget = QDoubleSpinBox()
                widget.setDecimals(setting.decimals)
                widget.setRange(
                    float(setting.minimum if setting.minimum is not None else -999999),
                    float(setting.maximum if setting.maximum is not None else 999999),
                )
                widget.setSingleStep(float(setting.step or 0.1))
                widget.setValue(float(value))
                widget.valueChanged.connect(self.changed.emit)
            else:
                widget = QComboBox()
                for label, choice_value in setting.choices:
                    widget.addItem(label, choice_value)
                index = widget.findData(str(value))
                widget.setCurrentIndex(index if index >= 0 else 0)
                widget.currentIndexChanged.connect(self.changed.emit)
            widget.setToolTip(setting.tooltip)
            self._widgets[setting.key] = widget
            self.add(setting.key, f"{setting.label}:", widget)

    def values(self) -> dict[str, bool | int | float | str]:
        result: dict[str, bool | int | float | str] = {}
        for setting in self._settings:
            widget = self._widgets[setting.key]
            if isinstance(widget, QCheckBox):
                result[setting.key] = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                result[setting.key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                result[setting.key] = widget.value()
            elif isinstance(widget, QComboBox):
                result[setting.key] = str(widget.currentData())
        return result

    def set_values(self, values: dict | None) -> None:
        supplied = dict(values or {})
        for setting in self._settings:
            if setting.key not in supplied:
                continue
            widget = self._widgets[setting.key]
            value = supplied[setting.key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QComboBox):
                index = widget.findData(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)

    def _clear(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._rows.clear()
        self._widgets.clear()


class VieneuGroup(_Group):
    def __init__(self) -> None:
        super().__init__()
        self.codec_combo = self.add("codec", "Codec:", QComboBox(), "vieneu_codec")
        self.temperature = self.add(
            "sampling_temp", "Temperature:",
            dspin_for("temperature", 0.8), "vieneu_temperature",
        )
        self.top_k = self.add(
            "sampling_topk", "Top-K:", spin_for("top_k", 50), "vieneu_top_k",
        )
        self.emotion_combo = self.add(
            "emotion", "Cảm xúc:", make_combo(EMOTION_FALLBACK, "natural"), "vieneu_emotion",
        )


class PiperGroup(_Group):
    STANDARD = (0.667, 0.800)
    VBEE = (0.900, 0.650)

    def __init__(self) -> None:
        super().__init__()
        self.preset = QComboBox()
        self.preset.addItem("Piper chuẩn", "standard")
        self.preset.addItem("Vbee tham chiếu", "vbee")
        self.preset.addItem("Tùy chỉnh", "custom")
        self.add("preset", "Hồ sơ:", self.preset, "piper_preset")
        self.noise_scale = self.add(
            "noise_scale", "Noise Scale:",
            dspin_for("piper_noise_scale", self.STANDARD[0]), "piper_noise_scale",
        )
        self.noise_w = self.add(
            "noise_w", "Noise W:",
            dspin_for("piper_noise_w", self.STANDARD[1]), "piper_noise_w",
        )
        self.seed = self.add(
            "seed", "Seed (-1 = ngẫu nhiên):",
            spin_for("piper_seed", -1), "piper_seed",
        )
        self.recommendation = QLabel("")
        self.recommendation.setWordWrap(True)
        self.recommendation.setObjectName("hint")
        self.recommendation.setToolTip(tooltip("piper_recommendation"))
        self.add("recommendation", "Khuyến nghị:", self.recommendation)
        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.noise_scale.valueChanged.connect(self._sync_preset)
        self.noise_w.valueChanged.connect(self._sync_preset)
        self._sync_preset()

    def _apply_preset(self, *_args) -> None:
        preset_id = str(self.preset.currentData() or "custom")
        values = self.STANDARD if preset_id == "standard" else self.VBEE if preset_id == "vbee" else None
        if values is None:
            return
        self.noise_scale.setValue(values[0])
        self.noise_w.setValue(values[1])

    def _sync_preset(self, *_args) -> None:
        values = (round(self.noise_scale.value(), 3), round(self.noise_w.value(), 3))
        preset_id = (
            "standard" if values == self.STANDARD
            else "vbee" if values == self.VBEE
            else "custom"
        )
        self.preset.blockSignals(True)
        index = self.preset.findData(preset_id)
        self.preset.setCurrentIndex(index)
        self.preset.blockSignals(False)


class F5Group(_Group):
    def __init__(self) -> None:
        super().__init__()
        self.nfe = self.add("nfe", "NFE step:", spin_for("f5_nfe_step", 32), "f5_nfe")
        self.cfg = self.add(
            "cfg", "CFG strength:", dspin_for("f5_cfg_strength", 2.0), "f5_cfg",
        )
        self.sway = self.add(
            "sway", "Sway sampling:", dspin_for("f5_sway_sampling_coef", -1.0), "f5_sway",
        )
        self.crossfade = self.add(
            "crossfade", "Cross-fade (giây):",
            dspin_for("f5_cross_fade_duration", 0.15), "f5_crossfade",
        )
        self.rms = self.add("rms", "Target RMS:", dspin_for("f5_target_rms", 0.1), "f5_rms")
        self.fix_duration = self.add(
            "fixdur", "Fix duration (giây, 0 = tắt):",
            dspin_for("f5_fix_duration", 0.0), "f5_fix_duration",
        )
        self.seed = self.add(
            "seed", "Seed (-1 = ngẫu nhiên):", spin_for("f5_seed", -1), "f5_seed",
        )
        self.remove_silence = QCheckBox("Bỏ khoảng lặng thừa")
        self.remove_silence.setToolTip(tooltip("f5_remove_silence"))
        self._rows["remove_silence"] = self.form.rowCount()
        self.form.addRow(self.remove_silence)


class ChatterboxGroup(_Group):
    def __init__(self) -> None:
        super().__init__()
        self.temperature = self.add(
            "temp", "Temperature:",
            dspin_for("chatterbox_temperature", 0.8), "chatterbox_temperature",
        )
        self.top_p = self.add(
            "top_p", "Top-P:", dspin_for("chatterbox_top_p", 0.95), "chatterbox_top_p",
        )
        self.top_k = self.add(
            "top_k", "Top-K:", spin_for("chatterbox_top_k", 1000), "chatterbox_top_k",
        )
        self.repetition = self.add(
            "rep", "Repetition penalty:",
            dspin_for("chatterbox_repetition_penalty", 1.2), "chatterbox_repetition",
        )
        self.seed = self.add(
            "seed", "Seed (-1 = ngẫu nhiên):",
            spin_for("chatterbox_seed", -1), "chatterbox_seed",
        )
        self.norm_loudness = QCheckBox("Chuẩn hoá âm lượng")
        self.norm_loudness.setChecked(True)
        self.norm_loudness.setToolTip(tooltip("chatterbox_norm_loudness"))
        self._rows["norm"] = self.form.rowCount()
        self.form.addRow(self.norm_loudness)
