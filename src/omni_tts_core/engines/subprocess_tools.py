from __future__ import annotations

import subprocess
import time
from threading import Event
from typing import Callable, Mapping, Sequence

from omni_tts_core.progress import check_cancel


def run_worker_process(
    command: Sequence[str],
    cwd: str,
    env: Mapping[str, str],
    timeout: float,
    cancel_event: Event | None,
    tick_callback: Callable[[], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
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
                    process.kill()
                    process.communicate()
                    raise
            if time.monotonic() - started_at > timeout:
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
                process.kill()
                process.communicate()
                raise
