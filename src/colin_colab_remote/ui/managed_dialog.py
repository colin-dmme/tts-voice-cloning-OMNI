"""User supervision of the same durable Colab queue used by MCP."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout,
)

from omni_tts_ui_qt.background import FunctionTask

from ..client import ColabClient
from ..google_mcp import GoogleColabProvider
from ..settings import ColabSettings, SettingsStore, data_root


STATES = {"queued": "Chờ", "running": "Đang chạy", "cancelling": "Đang hủy",
          "waiting": "Cần xử lý", "succeeded": "Audio đã xong", "cancelled": "Đã hủy",
          "failed": "Thất bại", "allocating": "Đang cấp máy", "session": "Đang mở phiên",
          "pairing": "Đang ghép worker", "launching": "Đang cài môi trường",
          "warming": "Đang tải model", "ready": "Sẵn sàng", "release_pending": "Đang trả máy"}


class ManagedColabDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colab tự động")
        self.resize(900, 700)
        self.client = ColabClient()
        self.preferences = SettingsStore()
        self.flow = None
        self._pending = set()
        self._refreshing = False
        self._jobs = {}
        layout = QVBoxLayout(self)
        note = QLabel("Gửi việc từ Studio hoặc MCP. Bộ điều phối giữ tiến độ khi bạn đóng cửa sổ này.\n"
                      "Kết nối tài khoản một lần, chọn GPU và thời hạn sử dụng trước khi bật tự động.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.enabled = QCheckBox("Tự cấp Colab khi chọn thiết bị Colab từ xa")
        self.account = QComboBox()
        for index in range(1, 4):
            self.account.addItem(f"Google AI Pro {index}", f"google-pro-{index}")
        self.gpu = QComboBox()
        self.gpu.addItems(["T4", "L4", "A100", "H100"])
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 600)
        self.minutes.setSuffix(" phút")
        self.auto_release = QCheckBox("Tự trả runtime do Studio cấp khi xong hoặc hủy việc")
        self.start_broker = QCheckBox("Tự bật broker trên PC khi cần")
        self.resume_at_logon = QCheckBox("Khôi phục hàng đợi khi đăng nhập Windows")
        form.addRow(self.enabled)
        form.addRow("Tài khoản", self.account)
        form.addRow("GPU yêu cầu", self.gpu)
        form.addRow("Thời gian tối đa mỗi runtime", self.minutes)
        form.addRow(self.auto_release)
        form.addRow(self.start_broker)
        form.addRow(self.resume_at_logon)
        layout.addLayout(form)
        settings = self.preferences.load()
        self.enabled.setChecked(settings.enabled)
        self.account.setCurrentIndex(self.account.findData(settings.account_id))
        self.gpu.setCurrentText(settings.accelerator)
        self.minutes.setValue(settings.max_runtime_minutes)
        self.auto_release.setChecked(settings.auto_release)
        self.start_broker.setChecked(settings.start_broker)
        self.resume_at_logon.setChecked(settings.resume_at_logon)
        row = QHBoxLayout()
        self.save_button = QPushButton("Lưu thiết lập")
        self.import_button = QPushButton("Chọn JSON OAuth Desktop")
        self.auth_button = QPushButton("Kết nối / cấp lại quyền Google")
        self.refresh_button = QPushButton("Làm mới")
        for button in (self.save_button, self.import_button, self.auth_button, self.refresh_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.auth_label = QLabel()
        self.auth_label.setWordWrap(True)
        layout.addWidget(self.auth_label)
        self.auth_link = QTextBrowser()
        self.auth_link.setMaximumHeight(75)
        self.auth_link.setOpenExternalLinks(True)
        self.auth_link.hide()
        layout.addWidget(self.auth_link)
        self.runtime_label = QLabel("Đang đọc trạng thái")
        self.runtime_label.setWordWrap(True)
        layout.addWidget(self.runtime_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Job", "Trạng thái", "Tiến độ", "Đoạn đã kiểm", "Thông báo"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for text, action in (("Tạm dừng cấp việc", "pause"), ("Tiếp tục", "resume"), ("Hủy job", "cancel")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, action=action: self.control(action))
            actions.addWidget(button)
        self.release_button = QPushButton("Dừng việc và giải phóng runtime")
        self.release_button.clicked.connect(lambda: self._run(self.client.release))
        actions.addWidget(self.release_button)
        layout.addLayout(actions)
        self.details = QTextBrowser()
        self.details.setMaximumHeight(140)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.save_button.clicked.connect(self.save)
        self.import_button.clicked.connect(self.import_client)
        self.auth_button.clicked.connect(self.start_auth)
        self.refresh_button.clicked.connect(self.refresh)
        self.account.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.show_job)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def provider(self):
        return GoogleColabProvider(data_root(), self.account.currentData())

    def _run(self, function, completed=None):
        task = FunctionTask(function)
        self._pending.add(task)
        def done(value):
            self._pending.discard(task)
            if completed:
                completed(value)
            self.refresh()
        def failed(message):
            self._pending.discard(task)
            self.details.setPlainText(message)
        task.signals.completed.connect(done)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def save(self):
        settings = ColabSettings.model_validate(self.preferences.load().model_dump() | {
            "enabled": self.enabled.isChecked(), "account_id": self.account.currentData(),
            "accelerator": self.gpu.currentText(), "max_runtime_minutes": self.minutes.value(),
            "auto_release": self.auto_release.isChecked(), "start_broker": self.start_broker.isChecked(),
            "resume_at_logon": self.resume_at_logon.isChecked()})
        self._run(lambda: self.client.configure(settings), lambda _: self.details.setPlainText("Đã lưu thiết lập Colab."))

    def import_client(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn OAuth Desktop JSON từ Google Cloud", "", "JSON (*.json)")
        if path:
            provider = self.provider()
            self._run(lambda: provider.configure_client(Path(path)))

    def start_auth(self):
        if self.flow:
            self.flow.close()
        provider = self.provider()
        def ready(flow):
            self.flow = flow
            self.auth_link.setHtml(f'<a href="{escape(flow.url, quote=True)}">Mở trang Google để chọn đúng tài khoản và cấp quyền</a>')
            self.auth_link.show()
        self._run(provider.begin_auth, ready)

    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            status = self.client.status()
            status["jobs"] = [item for item in status["jobs"] if item["job_id"].startswith("colab-")]
            auth = self.provider().auth_status()
            self.auth_label.setText("Google đã kết nối" + (f" · {auth['email']}" if auth.get("email") else "")
                if auth["authorized"] else "Cần cấp quyền Google" if auth["configured"] else "Chọn cấu hình OAuth Desktop để bắt đầu")
            if self.flow:
                result = self.flow.status()
                if result["state"] not in {"pending", "exchanging"}:
                    self.auth_link.hide()
                    if result["state"] != "complete":
                        self.details.setPlainText(result.get("message", "Cần cấp lại quyền Google."))
            runtime = status["runtime"]
            phase = STATES.get(runtime.get("phase"), runtime.get("phase", "Chưa cấp runtime"))
            self.runtime_label.setText(f"Runtime · {phase} · {runtime.get('account_id', '')} · {runtime.get('spec', {}).get('accelerator', '')}"
                + ("\n" + status["cleanup_error"] if status.get("cleanup_error") else ""))
            selected = self.selected_job()
            self._jobs = {item["job_id"]: item for item in status["jobs"]}
            self.table.blockSignals(True)
            self.table.setRowCount(len(status["jobs"]))
            for row, job in enumerate(status["jobs"]):
                values = [job["job_id"], "Tạm dừng" if job["paused"] else STATES.get(job["status"], job["status"]),
                          f"{job['progress']:.0f}%", str(job["verified_units"]), job["message"]]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))
                if job["job_id"] == selected:
                    self.table.selectRow(row)
            self.table.blockSignals(False)
            self.show_job()
        except Exception as error:
            self.details.setPlainText(str(error))
        finally:
            self._refreshing = False

    def selected_job(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.text() if item else None

    def control(self, action):
        job_id = self.selected_job()
        if job_id:
            self._run(lambda: self.client.control(job_id, action))

    def show_job(self):
        job_id = self.selected_job()
        if job_id:
            job = self._jobs.get(job_id, {})
            lines = [item["time"] + "  " + item["message"] for item in self.client.store.events(job_id, 20)]
            if job.get("error"):
                lines.append(job["error"])
            if job.get("result"):
                import json
                lines.append(json.dumps(job["result"], ensure_ascii=False, indent=2))
            self.details.setPlainText("\n".join(lines))

    def done(self, result):
        self.timer.stop()
        if self.flow:
            self.flow.close()
        super().done(result)
