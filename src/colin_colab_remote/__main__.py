from __future__ import annotations

import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Quản lý Colab từ xa của Colin TTS Studio")
    parser.add_argument("action", choices=("status", "panel", "supervisor"), default="status", nargs="?")
    args = parser.parse_args()
    if args.action == "panel":
        import sys
        from PySide6.QtWidgets import QApplication
        from .ui.managed_dialog import ManagedColabDialog
        app = QApplication.instance() or QApplication(sys.argv[:1])
        dialog = ManagedColabDialog()
        dialog.show()
        app.exec()
    elif args.action == "supervisor":
        from .daemon import ColabSupervisor
        from .settings import data_root
        ColabSupervisor(data_root()).run()
    else:
        from .client import ColabClient
        print(json.dumps(ColabClient().status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
