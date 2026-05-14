from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable

from omni_tts_shared.errors import GenerationCancelled


@dataclass(frozen=True)
class ProgressEvent:
    message: str
    current: float = 0.0
    total: float = 1.0

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(100.0, self.current / self.total * 100.0))


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    message: str,
    current: float = 0.0,
    total: float = 1.0,
) -> None:
    if callback:
        callback(ProgressEvent(message=message, current=current, total=total))


def check_cancel(cancel_event: Event | None) -> None:
    if cancel_event and cancel_event.is_set():
        raise GenerationCancelled("Đã hủy tác vụ tạo audio.")
