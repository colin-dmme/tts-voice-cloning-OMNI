from __future__ import annotations

import subprocess
import time
from threading import Event
from typing import Callable, Mapping, Sequence

import psutil

from omni_tts_core.progress import check_cancel


class WorkerProcessControl:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self._suspended: list[psutil.Process] = []
        self._suspended_at: float | None = None
        self.total_suspended_seconds = 0.0

    @property
    def is_suspended(self) -> bool:
        return self._suspended_at is not None

    def suspend(self) -> None:
        if self.is_suspended or self.process.poll() is not None:
            return
        try:
            root = psutil.Process(self.process.pid)
            targets = [*root.children(recursive=True), root]
        except psutil.Error as exc:
            raise RuntimeError(f"Không lấy được tiến trình worker để tạm dừng: {exc}") from exc
        suspended = []
        try:
            for target in targets:
                try:
                    target.suspend()
                    suspended.append(target)
                except psutil.NoSuchProcess:
                    continue
        except psutil.Error as exc:
            for target in reversed(suspended):
                try:
                    target.resume()
                except psutil.Error:
                    pass
            raise RuntimeError(f"Không tạm dừng được worker: {exc}") from exc
        self._suspended = suspended
        self._suspended_at = time.monotonic()

    def resume(self) -> None:
        if not self.is_suspended:
            return
        for target in reversed(self._suspended):
            try:
                target.resume()
            except psutil.Error:
                pass
        self.total_suspended_seconds += max(0.0, time.monotonic() - (self._suspended_at or 0.0))
        self._suspended = []
        self._suspended_at = None


def run_worker_process(
    command: Sequence[str],
    cwd: str,
    env: Mapping[str, str],
    timeout: float,
    cancel_event: Event | None,
    tick_callback: Callable[[], None] | None = None,
    supervisor_callback: Callable[[WorkerProcessControl], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    control = WorkerProcessControl(process)
    started_at = time.monotonic()
    while True:
        try:
            stdout, stderr = process.communicate(timeout=0.2)
            return subprocess.CompletedProcess(
                args=list(command),
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            if tick_callback is not None:
                try:
                    tick_callback()
                except Exception:
                    control.resume()
                    process.kill()
                    process.communicate()
                    raise
            if supervisor_callback is not None:
                try:
                    supervisor_callback(control)
                except Exception:
                    control.resume()
                    process.kill()
                    process.communicate()
                    raise
            active_seconds = time.monotonic() - started_at - control.total_suspended_seconds
            if active_seconds > timeout:
                control.resume()
                process.kill()
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(
                    cmd=list(command),
                    timeout=timeout,
                    output=stdout,
                    stderr=stderr,
                )
            try:
                check_cancel(cancel_event)
            except Exception:
                control.resume()
                process.kill()
                process.communicate()
                raise
