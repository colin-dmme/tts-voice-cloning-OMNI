"""Cross-process lock shared by every TTS entry point.

Desktop UIs and the MCP server can run in separate Python processes. This core
primitive serializes model/GPU access without putting policy in a GUI or
transport adapter.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Callable, Iterator

from filelock import FileLock, Timeout

from omni_tts_core.progress import check_cancel


class GenerationProcessLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def acquire(
        self,
        cancel_event: Event | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self.path))
        announced = False
        while True:
            check_cancel(cancel_event)
            try:
                lock.acquire(timeout=0.25)
                break
            except Timeout:
                if status_callback is not None and not announced:
                    status_callback("Đang chờ tác vụ TTS ở tiến trình khác hoàn tất...")
                    announced = True
        try:
            yield
        finally:
            lock.release()