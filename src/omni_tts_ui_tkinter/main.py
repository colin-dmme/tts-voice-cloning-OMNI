from __future__ import annotations

from omni_tts_core.config import AppSettings
from omni_tts_ui_tkinter.app import TkinterApp
from omni_tts_ui_tkinter.dnd import create_root


def main() -> None:
    settings = AppSettings()
    root = create_root(settings.app_display_name)
    TkinterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
