from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.app_controller import AppController
from omni_tts_core.provider_registry import provider_descriptor
from omni_tts_ui_qt.context import AppContext
from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
from omni_tts_ui_qt.pages.settings_sections import DeclarativeProviderGroup
from omni_tts_ui_qt.preferences import QtPreferences
from omni_tts_ui_qt.widgets.wheel_guard import install_parameter_wheel_guard


class ParameterWheelGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        install_parameter_wheel_guard(cls.app)

    @staticmethod
    def _wheel(target: QWidget, delta: int = -120) -> None:
        event = QWheelEvent(
            QPointF(4, 4),
            QPointF(4, 4),
            QPoint(),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(target, event)

    def test_wheel_does_not_change_spin_or_combo(self) -> None:
        spin = QSpinBox()
        spin.setRange(0, 10)
        spin.setValue(5)
        combo = QComboBox()
        combo.addItems(["Một", "Hai", "Ba"])
        combo.setCurrentIndex(1)

        self._wheel(spin)
        self._wheel(combo)

        self.assertEqual(spin.value(), 5)
        self.assertEqual(combo.currentIndex(), 1)

    def test_wheel_over_parameter_scrolls_nearest_page(self) -> None:
        area = QScrollArea()
        area.resize(240, 120)
        content = QWidget()
        content.setMinimumHeight(900)
        layout = QVBoxLayout(content)
        spin = QSpinBox()
        spin.setValue(5)
        layout.addWidget(spin)
        layout.addStretch()
        area.setWidget(content)
        area.setWidgetResizable(True)
        area.show()
        QApplication.processEvents()
        before = area.verticalScrollBar().value()

        self._wheel(spin)

        self.assertEqual(spin.value(), 5)
        self.assertGreater(area.verticalScrollBar().value(), before)
        area.close()


class ZeroTtsDeclarativeSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qt_group_renders_and_round_trips_every_setting(self) -> None:
        descriptor = provider_descriptor("zerotts")
        assert descriptor is not None
        group = DeclarativeProviderGroup()

        group.configure(descriptor.settings)

        self.assertEqual(group.form.rowCount(), 22)
        self.assertEqual(
            set(group.values()), {item.key for item in descriptor.settings}
        )
        self.assertTrue(all(widget.toolTip() for widget in group._widgets.values()))
        changed_events: list[bool] = []
        group.changed.connect(lambda: changed_events.append(True))

        group.set_values(
            {
                "normalize_vi_text": False,
                "audio_temperature": 1.1,
                "audio_topk": 77,
                "seed": 42,
                "streaming_decoder": False,
            }
        )
        values = group.values()
        self.assertFalse(values["normalize_vi_text"])
        self.assertAlmostEqual(values["audio_temperature"], 1.1)
        self.assertEqual(values["audio_topk"], 77)
        self.assertEqual(values["seed"], 42)
        self.assertFalse(values["streaming_decoder"])
        self.assertGreaterEqual(len(changed_events), 5)
        group.close()

    def test_v3_ui_offers_remote_preset_and_clone_but_v2_has_no_remote_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = AppContext(
                controller=AppController(), probe=Mock(), safety_gate=Mock(),
                preferences=QtPreferences(path=Path(temp_dir) / "ui_qt.json"),
                log=Mock(), set_worker_status=Mock(), show_page=Mock(), register_settings_provider=Mock(),
            )
            panel = SettingsPanel(context)
            panel._select_model("vieneu_v3_turbo")
            self.assertFalse(panel.remote_compute_section.isHidden())
            self.assertGreaterEqual(panel.device_combo.findData("remote"), 0)
            self.assertGreaterEqual(panel.fixed_voice_combo.findData("Ngọc Huyền"), 0)
            self.assertEqual(panel.fixed_voice_combo.count(), 23)
            self.assertFalse(panel.mode_profile.isHidden())
            panel.device_combo.setCurrentIndex(panel.device_combo.findData("remote"))
            panel.mode_fixed.setChecked(True)
            panel.fixed_voice_combo.setCurrentIndex(panel.fixed_voice_combo.findData("Ngọc Huyền"))
            settings = panel.current_settings()
            self.assertEqual(settings.runtime_target, "remote")
            self.assertEqual(settings.speaker_id, "Ngọc Huyền")
            self.assertEqual(settings.voice_source_mode, "fixed")
            panel._select_model("vieneu_v2_standard")
            self.assertTrue(panel.remote_compute_section.isHidden())
            self.assertEqual(panel.device_combo.findData("remote"), -1)
            panel.close()

    def test_settings_panel_keeps_provider_options_per_zerotts_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences = QtPreferences(path=Path(temp_dir) / "ui_qt.json")
            context = AppContext(
                controller=AppController(),
                probe=Mock(),
                safety_gate=Mock(),
                preferences=preferences,
                log=Mock(),
                set_worker_status=Mock(),
                show_page=Mock(),
                register_settings_provider=Mock(),
            )
            panel = SettingsPanel(context)

            provider_index = panel.provider_combo.findData("zerotts")
            self.assertGreaterEqual(provider_index, 0)
            self.assertEqual(
                panel.provider_combo.itemText(provider_index), "ZeroTTS (4)"
            )

            panel._select_model("zerotts_202m_gguf_q8_0")
            self.assertEqual(panel.current_model_id(), "zerotts_202m_gguf_q8_0")
            self.assertEqual(len(panel.declarative_provider_group.values()), 20)
            panel.declarative_provider_group.set_values({"audio_topk": 31})

            panel._select_model("zerotts_202m_gguf_q4_0")
            self.assertEqual(panel.current_model_id(), "zerotts_202m_gguf_q4_0")
            panel.declarative_provider_group.set_values({"audio_topk": 47})

            panel._select_model("zerotts_202m_gguf_q8_0")
            self.assertEqual(
                panel.declarative_provider_group.values()["audio_topk"], 31
            )
            panel._select_model("zerotts_202m_gguf_q4_0")
            self.assertEqual(
                panel.declarative_provider_group.values()["audio_topk"], 47
            )

            panel._select_model("zerotts_202m_official")
            onnx_values = panel.declarative_provider_group.values()
            self.assertEqual(len(onnx_values), 22)
            self.assertIn("cfg_scale", onnx_values)
            self.assertIn("warmup", onnx_values)
            panel.close()


if __name__ == "__main__":
    unittest.main()
