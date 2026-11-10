"""The CPU workers management page on the Studio navigation rail."""
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..mcp_tools import admin_profile
from ..targets import profile_store
from .pc_devices_dialog import PcDevicesDialog


def pc_workers_page(_context) -> QWidget:
    profile = admin_profile()
    message = "Cần cấu hình broker trong Studio trước khi ghép máy CPU."
    if profile is not None:
        try:
            return PcDevicesDialog(profile, profile_store(), embedded=True)
        except ValueError as error:
            message = str(error)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel(message))
    layout.addStretch()
    return page
