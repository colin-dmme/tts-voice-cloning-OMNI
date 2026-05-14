from __future__ import annotations

import logging
import subprocess
import sys

# ── Hide ALL subprocess console windows on Windows ──
# Must be applied before any library (pydub, etc.) spawns subprocesses.
if sys.platform == "win32":
    _original_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init

from omni_tts_ui_tkinter.app import TkinterApp

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')


def main() -> None:
    app = TkinterApp()
    app.run()


if __name__ == "__main__":
    main()
