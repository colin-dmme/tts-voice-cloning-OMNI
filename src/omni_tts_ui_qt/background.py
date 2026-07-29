"""Background threading: telemetry, one-shot tasks, and generation workers.

Worker threads never touch widgets. They emit Qt signals (queued connections)
so results marshal onto the GUI thread — the Qt equivalent of tkinter's
``root.after``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from omni_tts_core.app_controller import AppController, FileGenerationEvent
from omni_tts_core.hardware_monitor import HardwareProbe
from omni_tts_core.progress import ProgressEvent
from omni_tts_core.ui_presenters.settings_state import GenerationSettings


class TelemetryThread(QThread):
    snapshot_ready = Signal(object)  # HardwareSnapshot

    def __init__(self, probe: HardwareProbe, interval_ms: int = 2000, parent=None) -> None:
        super().__init__(parent)
        self.probe = probe
        self.interval_ms = interval_ms

    def run(self) -> None:
        while not self.isInterruptionRequested():
            try:
                self.snapshot_ready.emit(self.probe.snapshot())
            except Exception:  # telemetry must never crash the thread
                pass
            remaining = self.interval_ms
            while remaining > 0 and not self.isInterruptionRequested():
                wait = min(remaining, 100)
                self.msleep(wait)
                remaining -= wait


class TaskSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class FunctionTask(QRunnable):
    """Run a blocking service call (download/install/save) off the GUI thread."""

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as error:  # GUI boundary reports background failures
            self.signals.failed.emit(str(error))
        else:
            self.signals.completed.emit(result)


class AuthoringWorker(QThread):
    """Cancellable AI-authoring worker; never touches a widget directly."""

    completed = Signal(object)  # AuthoringSession
    failed = Signal(str)
    notice = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        controller: AppController,
        *,
        source_text: str,
        brief,
        voice_context,
        dialect_id: str,
        parent_candidate_id: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._source_text = source_text
        self._brief = brief
        self._voice_context = voice_context
        self._dialect_id = dialect_id
        self._parent_candidate_id = parent_candidate_id
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            result = self._controller.generate_authoring_candidates(
                self._source_text,
                self._brief,
                self._voice_context,
                self._dialect_id,
                parent_candidate_id=self._parent_candidate_id,
                on_notice=self.notice.emit,
                cancel_event=self._cancel_event,
            )
        except Exception as error:
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(error))
        else:
            self.completed.emit(result)


class GenerationWorker(QThread):
    progress_event = Signal(object)  # ProgressEvent
    file_event = Signal(object)  # FileGenerationEvent
    completed = Signal(object)  # GenerateSpeechResult | list[FileGenerationOutcome]
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        controller: AppController,
        mode: str,  # "text" | "files"
        settings: GenerationSettings,
        *,
        text: str = "",
        tasks: list[tuple[str, Path]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mode = mode
        self._settings = settings
        self._text = text
        self._tasks = tasks or []
        self._cancel_event = Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        from omni_tts_shared.errors import GenerationCancelled

        def on_progress(event: ProgressEvent) -> None:
            self.progress_event.emit(event)

        def on_file_event(event: FileGenerationEvent) -> None:
            self.file_event.emit(event)

        try:
            if self._mode == "text":
                result = self._controller.generate_text(
                    self._text, self._settings, on_progress, self._cancel_event
                )
            else:
                result = self._controller.generate_files(
                    self._tasks, self._settings, on_progress, on_file_event, self._cancel_event
                )
        except GenerationCancelled:
            self.cancelled.emit()
        except Exception as error:  # surface to GUI
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
