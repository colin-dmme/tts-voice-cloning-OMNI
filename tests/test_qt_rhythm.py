from __future__ import annotations

from unittest.mock import Mock

import pytest


@pytest.fixture
def panel(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from omni_tts_core.app_controller import AppController
    from omni_tts_ui_qt.context import AppContext
    from omni_tts_ui_qt.pages.settings_panel import SettingsPanel
    from omni_tts_ui_qt.preferences import QtPreferences

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    log = Mock()
    widget = SettingsPanel(AppContext(
        controller=AppController(), probe=Mock(), safety_gate=Mock(),
        preferences=QtPreferences(path=tmp_path / "ui_qt.json"),
        log=log, set_worker_status=Mock(), show_page=Mock(), register_settings_provider=Mock(),
    ))
    widget.test_log = log
    yield widget
    widget.close()
    app.processEvents()


FULL = {"enabled": True, "scope": "full"}


def _badge(panel, layer: str) -> str:
    return panel.narrative_pacing._badges[layer].text()


def test_kokoro_full_scope_shows_model_badges_and_locks_old_controls(panel):
    panel.load_preferences({"model_id": "kokoro_82m_v1_timestamped_onnx", "split_output": False,
                            "narrative_pacing": FULL})
    assert "MODEL" in _badge(panel, "comma")
    assert "APP" in _badge(panel, "paragraph")
    assert not panel.punctuation_section.activation.isEnabled()
    assert "NHỊP ĐỌC" in panel.punctuation_section.activation.text()
    assert not panel.paragraph_pause_editor.isEnabled()
    assert panel.narrative_pacing.switch_box.isVisibleTo(panel.narrative_pacing)
    assert "kokoro_pause_mode" in panel.narrative_pacing._switch_widgets


def test_switching_model_logs_changes_and_locks_provider_setting(panel):
    panel.load_preferences({"model_id": "kokoro_82m_v1_timestamped_onnx", "split_output": False,
                            "narrative_pacing": FULL})
    panel._select_model("zerotts_202m_official")
    # The value is kept (Core drops it at generation time); only the widget is locked.
    gap = panel.declarative_provider_group._widgets["segment_gap_seconds"]
    assert not gap.isEnabled()
    logged = " ".join(str(call.args[0]) for call in panel.test_log.call_args_list)
    assert "Nhịp đọc" in logged and "MODEL" in logged


def test_pacing_only_scope_leaves_old_controls_alone(panel):
    panel.load_preferences({"model_id": "piper_ngoc_huyen", "split_output": False,
                            "narrative_pacing": {"enabled": True, "scope": "pacing_only"}})
    assert panel.punctuation_section.activation.isEnabled()
    assert panel.paragraph_pause_editor.isEnabled()


def test_split_output_greys_between_paragraph_rows(panel):
    panel.load_preferences({"model_id": "piper_ngoc_huyen", "split_output": True,
                            "narrative_pacing": FULL})
    assert "KHÔNG ÁP DỤNG" in _badge(panel, "paragraph")
    assert not panel.narrative_pacing._mins["paragraph"].isEnabled()
    assert panel.narrative_pacing._mins["sentence_end"].isEnabled()


def test_ranges_round_trip_through_settings(panel):
    panel.load_preferences({"model_id": "piper_ngoc_huyen", "split_output": False,
                            "narrative_pacing": FULL})
    pacing = panel.narrative_pacing
    pacing._mins["sentence_end"].setValue(0.45)
    pacing._maxs["sentence_end"].setValue(0.6)
    options = pacing.options()
    assert options["layer_ranges"]["sentence_end"] == [450, 600]
    assert options["sentence_end_pause_ms"] == 450
    assert "ellipsis" not in options["layer_ranges"] or options["layer_ranges"]["ellipsis"]
    request = panel.current_settings().to_request("Xin chào")
    assert request.narrative_pacing.layer_ranges["sentence_end"] == [450, 600]
    assert request.narrative_pacing.scope == "full"


def test_preset_keeps_scope(panel):
    panel.load_preferences({"model_id": "piper_ngoc_huyen", "split_output": False,
                            "narrative_pacing": FULL})
    pacing = panel.narrative_pacing
    pacing.preset.setCurrentIndex(pacing.preset.findData("audiobook"))
    pacing.apply_preset.click()
    options = pacing.options()
    assert options["scope"] == "full"
    assert options["layer_ranges"]["sentence_end"] == [650, 750]
