"""Windows logon recovery for the independent Colab supervisor."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def configure_autostart(directory: Path, enabled: bool) -> None:
    if os.name != "nt":
        return
    from omni_tts_core.paths import PROJECT_ROOT
    python = Path(sys.executable)
    if python.with_name("pythonw.exe").is_file():
        python = python.with_name("pythonw.exe")
    script = Path(__file__).with_name("supervisor_task.ps1")
    process = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-Python", str(python), "-Project", str(PROJECT_ROOT),
        "-DataDirectory", str(directory.resolve()), "-Mode", "enable" if enabled else "disable"],
        stdin=subprocess.DEVNULL, capture_output=True, creationflags=0x08000000, timeout=20)
    if process.returncode:
        raise RuntimeError("Chưa đặt được tự khôi phục Colab khi đăng nhập Windows. Có thể bật lại trong bảng quản lý.")
