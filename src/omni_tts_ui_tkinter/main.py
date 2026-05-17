from __future__ import annotations

from omni_tts_core.config import AppSettings
from omni_tts_core.user_state import restore_user_state
from omni_tts_ui_tkinter.app import TkinterApp
from omni_tts_ui_tkinter.dnd import create_root


def main() -> None:
    restore_user_state()
    settings = AppSettings()
    root = create_root(settings.app_display_name)
    TkinterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
