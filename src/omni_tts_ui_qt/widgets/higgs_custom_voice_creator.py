from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool
from PySide6.QtWidgets import QInputDialog, QMessageBox, QPushButton, QWidget

from omni_tts_core.app_controller import AppController
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.background import FunctionTask


class HiggsCustomVoiceCreator(QObject):
    """Own the asynchronous Custom Voice creation workflow, not form state."""

    def __init__(
        self,
        parent: QWidget,
        controller: AppController,
        settings_provider: Callable[[], GenerationSettings],
        on_created: Callable[[object], None],
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.controller = controller
        self.settings_provider = settings_provider
        self.on_created = on_created
        self.button = QPushButton("Tạo Custom Voice từ Profile…", parent)
        self.button.setToolTip(
            "Gửi audio và transcript của một Profile tới API /v1/audio/voices, "
            "sau đó lưu voice_id để tái sử dụng."
        )
        self.button.clicked.connect(self.start)
        self._task: FunctionTask | None = None

    def start(self) -> None:
        profiles = self.controller.voice_profile_choices()
        if not profiles:
            QMessageBox.information(
                self.parent_widget,
                "Chưa có Voice Profile",
                "Hãy tạo Voice Profile có audio và transcript trước.",
            )
            return
        labels = [name for name, _profile_id in profiles]
        selected, ok = QInputDialog.getItem(
            self.parent_widget,
            "Nguồn cho Custom Voice",
            "Chọn Voice Profile:",
            labels,
            editable=False,
        )
        if not ok:
            return
        title, ok = QInputDialog.getText(
            self.parent_widget,
            "Tên Custom Voice",
            "Tên hiển thị trên API:",
            text=str(selected),
        )
        if not ok or not title.strip():
            return
        ownership = QMessageBox.question(
            self.parent_widget,
            "Xác nhận quyền sử dụng giọng",
            "Bạn xác nhận mình có quyền sử dụng và clone giọng trong Profile này?",
        )
        if ownership != QMessageBox.StandardButton.Yes:
            return
        profile_id = next(
            profile_id for name, profile_id in profiles if name == selected
        )
        settings = self.settings_provider()
        self.button.setEnabled(False)
        self.button.setText("Đang tạo Custom Voice…")
        task = FunctionTask(
            lambda: self.controller.create_higgs_custom_voice(
                settings, profile_id, title
            )
        )
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        self._task = task
        QThreadPool.globalInstance().start(task)

    def _completed(self, voice) -> None:
        self._reset_button()
        self.on_created(voice)
        QMessageBox.information(
            self.parent_widget,
            "Đã tạo Custom Voice",
            f"{voice.title}\nVoice ID: {voice.voice_id}",
        )

    def _failed(self, message: str) -> None:
        self._reset_button()
        QMessageBox.warning(
            self.parent_widget, "Không tạo được Custom Voice", message
        )

    def _reset_button(self) -> None:
        self.button.setEnabled(True)
        self.button.setText("Tạo Custom Voice từ Profile…")
