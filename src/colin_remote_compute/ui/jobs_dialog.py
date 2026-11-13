"""Live view of CPU jobs in the same queue used by the agent."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from omni_tts_ui_qt.background import FunctionTask
from ..client import ColabClient, public_job
from ..store import TERMINAL


_LABELS = {"queued": "Chờ", "running": "Đang chạy", "waiting": "Cần xử lý", "cancelling": "Đang hủy",
           "succeeded": "Đã xong", "cancelled": "Đã hủy", "failed": "Thất bại"}


class PcJobsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hàng đợi CPU từ xa")
        self.resize(860, 490)
        self.client = ColabClient()
        self.rows = {}
        self.task = None
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Máy", "Model", "Trạng thái", "Tiến độ", "Thông báo"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.actions = {}
        for label, action in (("Tạm dừng sau đoạn này", "pause"), ("Tiếp tục", "resume"), ("Hủy job", "cancel")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=action: self.control(value))
            self.actions[action] = button
            buttons.addWidget(button)
        self.work_folder = QPushButton("Thư mục làm việc")
        self.work_folder.clicked.connect(self.open_work_folder)
        buttons.addWidget(self.work_folder)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.note = QLabel()
        layout.addWidget(self.note)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        layout.addWidget(self.details)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.table.itemSelectionChanged.connect(self.show_job)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.refresh()

    def selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else ""

    def refresh(self):
        current = self.selected()
        rows = [public_job(item) for item in self.client.store.list(50) if item["job_id"].startswith("cpu-job-")]
        self.rows = {item["job_id"]: item for item in rows}
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            summary = item["request_summary"]
            status = "Tạm dừng" if item["paused"] else _LABELS.get(item["status"], item["status"])
            verified = self.client.store.state(item["job_id"] + ":verified_units", 0)
            values = (summary["execution"]["worker_name"], summary["model_id"], status,
                      f"{item['progress']:.0f}% · {verified} lượt đã kiểm", item["message"])
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setData(Qt.ItemDataRole.UserRole, item["job_id"])
                self.table.setItem(row, column, cell)
            if item["job_id"] == current:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.show_job()

    def show_job(self):
        job = self.rows.get(self.selected())
        self.work_folder.setEnabled(job is not None)
        active = job is not None and job["status"] not in TERMINAL and job["status"] != "cancelling"
        for action, button in self.actions.items():
            allowed = active and self.task is None
            if action == "pause":
                allowed = allowed and not job["paused"] and job["status"] in {"running", "queued"}
            elif action == "resume":
                allowed = allowed and (job["paused"] or job["status"] == "waiting")
            button.setEnabled(bool(allowed))
        if job is None:
            self.details.clear()
            return
        lines = [f"{row['time']}  {row['message']}" for row in self.client.store.events(job["job_id"], 12)]
        if job["error"]:
            lines.append(job["error"])
        if job["result"]:
            import json
            lines.append(json.dumps(job["result"], ensure_ascii=False))
        value = "\n".join(lines)
        if self.details.toPlainText() != value:
            self.details.setPlainText(value)

    def control(self, action):
        job_id = self.selected()
        if not job_id or self.task is not None:
            return
        self.task = FunctionTask(lambda: self.client.control(job_id, action))
        self.task.signals.completed.connect(lambda _result: self._done("Đã ghi yêu cầu."))
        self.task.signals.failed.connect(self._done)
        QThreadPool.globalInstance().start(self.task)
        self.show_job()

    def open_work_folder(self):
        if self.selected():
            from omni_tts_ui_qt.widgets.common import open_path
            open_path(self.client.work_dir(self.selected()))

    def _done(self, message):
        self.task = None
        self.note.setText(message)
        self.refresh()

    def done(self, result):
        if self.task is None:
            self.timer.stop()
            super().done(result)
