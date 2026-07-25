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

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QWidget

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
