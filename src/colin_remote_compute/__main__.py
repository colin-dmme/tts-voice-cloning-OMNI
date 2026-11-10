"""Open the CPU worker panel independently of the Studio window."""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .mcp_tools import admin_profile
    from .targets import profile_store
    from .ui.pc_devices_dialog import PcDevicesDialog

    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        profile = admin_profile()
        if profile is None:
            raise ValueError("Cần cấu hình broker trong Studio trước khi ghép máy CPU.")
        dialog = PcDevicesDialog(profile, profile_store())
    except (OSError, ValueError) as error:
        QMessageBox.warning(None, "Quản lý máy CPU", str(error))
        return 1
    dialog.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
