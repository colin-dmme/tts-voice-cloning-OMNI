from __future__ import annotations

import subprocess
import sys
import time
from threading import Event
from typing import Mapping, Sequence

from omni_tts_core.progress import check_cancel

# Windows: hide subprocess console windows
_POPEN_EXTRA: dict = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = subprocess.CREATE_NO_WINDOW


def run_worker_process(
    command: Sequence[str],
    cwd: str,
    env: Mapping[str, str],
    timeout: float,
    cancel_event: Event | None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **_POPEN_EXTRA,
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
