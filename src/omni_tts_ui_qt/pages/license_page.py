"""License page: status, machine id, import license file, recheck."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_ui_qt.context import AppContext


class LicensePage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel("Bản quyền")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("hint")
        layout.addWidget(self.detail_label)
        layout.addSpacing(10)

        machine_row = QHBoxLayout()
        machine_row.addWidget(QLabel("Mã máy:"))
        self.machine_edit = QLineEdit()
        self.machine_edit.setReadOnly(True)
        copy_button = QPushButton("Sao chép")
        copy_button.clicked.connect(self._copy_machine_id)
        machine_row.addWidget(self.machine_edit, 1)
        machine_row.addWidget(copy_button)
        layout.addLayout(machine_row)

        button_row = QHBoxLayout()
        import_button = QPushButton("Nhập file license")
        import_button.setObjectName("primaryButton")
        recheck_button = QPushButton("Kiểm tra lại")
        import_button.clicked.connect(self._import_license)
        recheck_button.clicked.connect(self.refresh)
        button_row.addWidget(import_button)
        button_row.addWidget(recheck_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()

        self.refresh()

    def refresh(self) -> None:
        try:
            status = self.ctrl.license_status()
            device_id = self.ctrl.current_device_id()
        except Exception as error:
            self.status_label.setText(f'<span style="color:#f87171">Không đọc được license: {error}</span>')
            return
        self.machine_edit.setText(device_id)
        if status.valid:
            self.status_label.setText('<span style="color:#34d399">● License hợp lệ</span>')
        else:
            self.status_label.setText('<span style="color:#f87171">● License chưa kích hoạt</span>')
        self.detail_label.setText(status.message)

    def _copy_machine_id(self) -> None:
        QApplication.clipboard().setText(self.machine_edit.text())
        self.context.log("Đã sao chép mã máy.")

    def _import_license(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file license", "", "License (*.json *.lic *.txt)")
        if not path:
            return
        try:
            self.ctrl.install_license(Path(path))
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", f"Không nhập được license: {error}")
            return
        self.refresh()
        self.context.log("Đã nhập file license.")
