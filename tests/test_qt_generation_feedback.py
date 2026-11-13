import os
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton

from omni_tts_core.progress import ProgressEvent
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.main_window import MainWindow
from omni_tts_ui_qt.pages import studio_page
from omni_tts_ui_qt.pages.studio_page import StudioPage
from omni_tts_ui_qt.theme import apply_theme


@pytest.fixture
def page(monkeypatch):
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    worker_factory = Mock()
    monkeypatch.setattr(studio_page, "GenerationWorker", worker_factory)
    page = SimpleNamespace(
        app=app, factory=worker_factory, ctrl=Mock(),
        context=SimpleNamespace(log=Mock(), set_worker_status=Mock()),
        settings_panel=SimpleNamespace(current_settings=lambda: GenerationSettings()),
        queue=Mock(is_running=Mock(return_value=False)),
        _text_worker=None, _text_active=False, _text_cancelling=False,
        _queue_active=False, _queue_status_message="", _text_status_message="",
        text_input=QPlainTextEdit("Một lượt thử"), output_stem=QLineEdit(),
        text_output_dir=QLineEdit(), text_suffix_check=QCheckBox(),
        text_progress_bar=QProgressBar(), text_job_label=QLabel(), result_view=QPlainTextEdit(),
        generate_button=QPushButton("Tạo giọng đọc"), text_cancel_button=QPushButton("Hủy"),
        text_preview_button=QPushButton(), text_open_folder_button=QPushButton(),
        text_copy_path_button=QPushButton(), text_copy_content_button=QPushButton(),
        _on_text_done=Mock(), _on_text_failed=Mock(), _on_text_cancelled=Mock(),
    )
    page.generate_button.setObjectName("primaryButton")
    for method in ("_on_text_progress", "_sync_global_worker_status"):
        setattr(page, method, MethodType(getattr(StudioPage, method), page))
    page.generate_button.clicked.connect(lambda: StudioPage._generate_text(page))
    page.text_cancel_button.clicked.connect(lambda: StudioPage._cancel_text(page))
    yield page


def test_generation_locks_button_and_cancellation_until_completion(page):
    page.generate_button.click()
    assert page.factory.call_count == 1
    assert not page.generate_button.isEnabled()
    assert page.generate_button.text() == "Đang xử lý…"
    assert page.text_cancel_button.isEnabled()
    assert page.context.log.call_count > 0
    # Guard the handler too, including programmatic submissions.
    page.generate_button.click()
    StudioPage._generate_text(page)
    assert page.factory.call_count == 1

    page.text_cancel_button.click()
    assert page.generate_button.text() == "Đang hủy…"
    assert not page.text_cancel_button.isEnabled()
    assert StudioPage.is_busy(page)
    page._text_worker.request_cancel.assert_called_once()
    page.text_cancel_button.click()
    assert page._text_worker.request_cancel.call_count == 1

    StudioPage._finish_text(page, "paused", "Đã hủy tạo giọng.")
    assert not StudioPage.is_busy(page)
    assert page.generate_button.isEnabled()
    assert page.generate_button.text() == "Tạo giọng đọc"
    assert not page.text_cancel_button.isEnabled()


def test_progress_ignores_empty_messages_and_updates_header(page):
    page._text_active = True
    page.text_job_label.setText("Đang chờ tác vụ trước")
    page._on_text_progress(ProgressEvent(""))
    assert page.text_job_label.text() == "Đang chờ tác vụ trước"
    page.context.log.assert_not_called()
    page._on_text_progress(ProgressEvent("Nhóm CPU · 28/219 đoạn đã xác minh · 2 máy", 28, 219))
    assert page.text_progress_bar.value() == 12
    assert page.context.set_worker_status.call_args.args[1] == page.text_job_label.text()


def test_disabled_primary_button_loses_purple_background(page):
    button = page.generate_button
    button.resize(180, 42)
    button.show()
    page.app.processEvents()
    active = button.grab().toImage().pixelColor(12, button.height() // 2)
    button.setEnabled(False)
    page.app.processEvents()
    disabled = button.grab().toImage().pixelColor(12, button.height() // 2)
    assert active != disabled
    button.close()


def test_system_log_skips_empty_events(page):
    window = SimpleNamespace(log_view=QPlainTextEdit())
    MainWindow.log(window, "")
    MainWindow.log(window, "  ")
    assert not window.log_view.toPlainText()
    MainWindow.log(window, "Đang xếp hàng")
    assert "Đang xếp hàng" in window.log_view.toPlainText()
