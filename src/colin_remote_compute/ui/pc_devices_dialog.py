"""Pair and control CPU workers from the Studio machine."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QSignalBlocker, QThreadPool, QTimer, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from colin_colab_remote.broker.models import WorkerProfile
from colin_colab_remote.broker.profiles import WorkerProfileStore
from colin_colab_remote.ui.colab_pairing_dialog import pairing_client
from omni_tts_ui_qt.background import FunctionTask
from omni_tts_shared.errors import GenerationError


_DESIRED = {"running": "Nhận việc", "paused": "Tạm ngừng", "stopped": "Dừng xử lý"}
_OBSERVED = {
    "starting": "Đang khởi động", "idle": "Sẵn sàng", "busy": "Đang xử lý",
    "paused": "Đã tạm ngừng", "stopped": "Đã dừng", "error": "Gặp lỗi",
}
_CONTROL = {"resume": "running", "pause": "paused", "stop": "stopped"}


def _seen_at(value: str | None) -> datetime | None:
    try:
        stamp = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _observed(device: dict) -> str:
    if device.get("revoked"):
        return "Đã ngắt quyền"
    stamp = _seen_at(device.get("last_seen_at"))
    if stamp is None:
        return "Chưa liên lạc"
    if (datetime.now(timezone.utc) - stamp).total_seconds() > 90:
        return "Mất liên lạc"
    return _OBSERVED.get(device.get("observed_state"), "Chưa rõ")


class PcDevicesDialog(QDialog):
    def __init__(self, broker_profile: WorkerProfile, store: WorkerProfileStore, parent=None, *, embedded=False) -> None:
        super().__init__(parent)
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.broker_profile, self.store = broker_profile, store
        address = urlsplit(broker_profile.broker_url)
        if (not address.hostname or address.username or address.password or address.query or address.fragment
                or address.scheme != "https" and address.hostname not in {"127.0.0.1", "::1", "localhost"}):
            raise ValueError("Cần địa chỉ broker HTTPS hoặc localhost để quản lý máy CPU.")
        self.client = pairing_client(broker_profile)
        self.selected_profile_id = ""
        self._preview: dict | None = None
        self._task: FunctionTask | None = None
        self._devices: list[dict] = []
        self._refresh_notice = ""
        self.setWindowTitle("Quản lý máy CPU")
        self.resize(940, 515)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nhập mã ghép nối hiện trên máy CPU, rồi kiểm tra thông tin trước khi cấp quyền."))
        pairing = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("ABCD-EFGH")
        self.code.setMaxLength(12)
        self.inspect_button = QPushButton("Kiểm tra mã")
        self.approve_button = QPushButton("Cấp quyền cho máy")
        self.inspect_button.setAutoDefault(False)
        self.approve_button.setAutoDefault(False)
        pairing.addWidget(self.code, 1)
        pairing.addWidget(self.inspect_button)
        pairing.addWidget(self.approve_button)
        layout.addLayout(pairing)
        self.preview_label = QLabel()
        self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_label.setWordWrap(True)
        self.preview_label.hide()
        layout.addWidget(self.preview_label)

        pool = QHBoxLayout()
        self.pool_summary = QLabel("Đang đọc danh sách máy…")
        pool.addWidget(self.pool_summary, 1)
        pool.addWidget(QLabel("Tối đa máy mỗi job"))
        self.pool_limit = QSpinBox()
        self.pool_limit.setRange(1, 16)
        self.pool_limit.setValue(store.load().cpu_pool_limit)
        self.pool_limit.setToolTip("Số máy được cấp đoạn cùng lúc khi chọn Tự chia tải.")
        self.pool_limit.editingFinished.connect(self._save_limit)
        pool.addWidget(self.pool_limit)
        layout.addLayout(pool)
        self.totals = QLabel("Tổng lượt nhận · đang đọc thống kê")
        self.totals.setWordWrap(True)
        layout.addWidget(self.totals)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Chia tải", "Máy", "Trạng thái", "Model đã cài", "Lượt nhận", "Hoàn tất", "WAV", "Liên lạc cuối"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Làm mới")
        self.choose_button = QPushButton("Chọn máy")
        self.pause_button = QPushButton("Tạm ngừng")
        self.resume_button = QPushButton("Cho nhận việc")
        self.stop_button = QPushButton("Dừng xử lý")
        self.revoke_button = QPushButton("Ngắt quyền")
        self.jobs_button = QPushButton("Hàng đợi CPU")
        self.pause_button.setToolTip("Ngừng nhận đoạn mới và để đoạn đang chạy hoàn tất.")
        self.stop_button.setToolTip("Hủy đoạn đang chạy và dừng nhận việc trên máy này.")
        for button in (self.refresh_button, self.choose_button, self.pause_button,
                       self.resume_button, self.stop_button, self.revoke_button, self.jobs_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.buttons.setVisible(not embedded)
        self.choose_button.setVisible(not embedded)

        self.code.textChanged.connect(self._clear_preview)
        self.code.returnPressed.connect(self.inspect_code)
        self.inspect_button.clicked.connect(self.inspect_code)
        self.approve_button.clicked.connect(self.approve)
        self.refresh_button.clicked.connect(lambda: self.refresh())
        self.table.itemSelectionChanged.connect(self._sync_controls)
        self.table.itemChanged.connect(self._toggle_pool)
        self.choose_button.clicked.connect(self.choose_device)
        self.pause_button.clicked.connect(lambda: self.control("pause"))
        self.resume_button.clicked.connect(lambda: self.control("resume"))
        self.stop_button.clicked.connect(lambda: self.control("stop"))
        self.revoke_button.clicked.connect(self.revoke)
        self.jobs_button.clicked.connect(self.show_jobs)
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self._refresh_when_visible)
        self.timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _refresh_when_visible(self):
        if self.isVisible() and not (self.code.hasFocus() and self.code.text().strip()) and self._preview is None:
            self.refresh()

    def _save_limit(self):
        try:
            self.store.set_cpu_pool_limit(self.pool_limit.value())
            self.status.setText("Đã lưu giới hạn máy cho các job mới.")
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(f"Chưa lưu được giới hạn máy. {error}")

    def _toggle_pool(self, item):
        if item.column() != 0:
            return
        device = self._devices[item.row()]
        enabled = item.checkState() == Qt.CheckState.Checked
        try:
            profile = self._saved_profile(device["worker_id"])
            if profile is None and enabled and not device.get("revoked"):
                self._save_profile(device)
                profile = self._saved_profile(device["worker_id"])
            if profile is None:
                raise ValueError("Cần ghép máy trước khi đưa vào nhóm CPU.")
            self.store.set_cpu_pool_worker(profile.profile_id, enabled)
            self.status.setText("Đã thêm máy vào nhóm chia tải." if enabled else "Đã bỏ máy khỏi lượt cấp đoạn mới.")
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(str(error))
        QTimer.singleShot(0, lambda: self._render_devices(self._devices))

    def _saved_profile(self, worker_id):
        return next((item for item in self.store.load().profiles if item.worker_id == worker_id
                     and item.is_pc and item.broker_url == self.broker_profile.broker_url), None)

    def show_jobs(self):
        from .jobs_dialog import PcJobsDialog
        PcJobsDialog(self).exec()

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        return self._devices[row] if 0 <= row < len(self._devices) else None

    def _sync_controls(self) -> None:
        idle = self._task is None
        device = self._selected()
        controllable = idle and device is not None and not device.get("revoked")
        desired = device.get("desired_state") if device is not None else None
        self.code.setEnabled(idle)
        self.inspect_button.setEnabled(idle)
        self.approve_button.setEnabled(idle and self._preview is not None)
        self.refresh_button.setEnabled(idle)
        self.choose_button.setEnabled(controllable)
        self.pause_button.setEnabled(controllable and desired == "running")
        self.resume_button.setEnabled(controllable and desired != "running")
        self.stop_button.setEnabled(controllable and desired != "stopped")
        self.revoke_button.setEnabled(controllable)
        self.buttons.setEnabled(idle)

    def _clear_preview(self) -> None:
        self._preview = None
        self.preview_label.hide()
        self._sync_controls()

    def _start(self, message, operation, complete) -> None:
        if self._task is not None:
            return
        self.status.setText(message)
        task = FunctionTask(operation)
        self._task = task
        self._sync_controls()
        task.signals.completed.connect(complete)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def refresh(self, notice: str = "") -> None:
        if self._task is not None:
            return
        self._refresh_notice = notice
        self._start("Đang đọc trạng thái máy CPU...", self._load_devices, self._refreshed)

    def _load_devices(self):
        devices = self.client.list_pc_devices()
        installed = {item.capabilities.worker_id: [model.model_id for model in item.capabilities.models]
                     for item in self.client.list_workers() if item.capabilities.worker_type == "remote_pc"}
        offset = datetime.now().astimezone().utcoffset()
        minutes = int(offset.total_seconds() // 60) if offset else 0

        def fetch(device):
            worker_id = device["worker_id"]
            try:
                totals = self.client.pc_statistics(worker_id, minutes).get("total")
            except GenerationError:
                totals = None
            return device | {"installed_models": installed.get(worker_id, []), "totals": totals}

        with ThreadPoolExecutor(max_workers=6) as executor:
            return list(executor.map(fetch, devices))

    @Slot(object)
    def _refreshed(self, devices: list[dict]) -> None:
        self._task = None
        self._render_devices(devices)
        self.status.setText(self._refresh_notice or f"Đã tải {len(devices)} hồ sơ máy CPU.")
        self._refresh_notice = ""

    def _render_devices(self, devices: list[dict]) -> None:
        current = self._selected()
        selected = (current or {}).get("worker_id", self.selected_profile_id)
        profiles = {item.worker_id: item for item in self.store.load().profiles
                    if item.is_pc and item.enabled and item.broker_url == self.broker_profile.broker_url}
        devices = sorted(devices, key=lambda row: (bool(row.get("revoked")),
                                                    (row.get("display_name") or row["worker_id"]).casefold()))
        self._devices = devices
        ready = included = paired = 0
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(devices))
            for row, device in enumerate(devices):
                worker_id = device["worker_id"]
                stamp = _seen_at(device.get("last_seen_at"))
                observed = _observed(device)
                desired = device.get("desired_state")
                profile = profiles.get(worker_id)
                allowed = bool(profile and profile.pool_enabled and not device.get("revoked"))
                included += int(allowed)
                paired += int(not device.get("revoked"))
                ready += int(observed in {"Sẵn sàng", "Đang xử lý"} and desired == "running")
                if observed in {"Sẵn sàng", "Đang xử lý"} and desired in {"paused", "stopped"}:
                    observed = "Chờ tạm ngừng" if desired == "paused" else "Chờ dừng"
                check = QTableWidgetItem()
                if not device.get("revoked"):
                    check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    check.setCheckState(Qt.CheckState.Checked if allowed else Qt.CheckState.Unchecked)
                    check.setToolTip("Đưa máy này vào lựa chọn Tự chia tải.")
                self.table.setItem(row, 0, check)
                counts = device.get("totals") or {}
                values = (
                    device.get("display_name") or worker_id,
                    observed,
                    ", ".join(device.get("installed_models") or []) or "—",
                    *(str(counts.get(key, "—")) for key in ("received", "completed", "wav_files")),
                    stamp.astimezone().strftime("%d/%m %H:%M:%S") if stamp else "—",
                )
                for column, value in enumerate(values, 1):
                    item = QTableWidgetItem(value)
                    tip = worker_id if column == 1 else value
                    if column == 2:
                        tip += " · " + _DESIRED.get(desired, "Chưa rõ")
                        if observed == "Sẵn sàng":
                            item.setForeground(QColor("#8adfae"))
                        elif observed == "Đang xử lý":
                            item.setForeground(QColor("#c4b5fd"))
                    item.setToolTip(tip)
                    self.table.setItem(row, column, item)
                if worker_id == selected:
                    self.table.selectRow(row)
        self.pool_summary.setText(f"{paired} máy đã ghép   ·   {ready} đang online nhận việc   ·   {included} trong nhóm")
        reports = [item["totals"] for item in devices if item.get("totals") is not None]
        if reports or not devices:
            received, completed, wavs = (sum(report.get(key, 0) for report in reports)
                                         for key in ("received", "completed", "wav_files"))
            partial = f"   ·   Có số liệu {len(reports)}/{len(devices)} máy" if len(reports) != len(devices) else ""
            self.totals.setText(f"Tổng lượt nhận {received}   ·   Hoàn tất {completed}   ·   WAV {wavs}{partial}")
        else:
            self.totals.setText("Chưa đọc được số liệu từ broker.")
        self._sync_controls()

    def inspect_code(self) -> None:
        if self._task is not None:
            return
        self._clear_preview()
        code = self.code.text().strip().upper()
        compact = code.replace("-", "").replace(" ", "")
        if len(compact) != 8 or not compact.isascii() or not compact.isalnum():
            self.status.setText("Nhập mã 8 ký tự hiện trên máy CPU, ví dụ ABCD-EFGH.")
            return
        self._start("Đang kiểm tra mã ghép máy...", lambda: self.client.inspect_pc_pairing(code), self._inspected)

    @Slot(object)
    def _inspected(self, preview: dict) -> None:
        self._task = None
        models = preview.get("models") or []
        if not (preview.get("pairing_id") and preview.get("worker_id", "").startswith("pc-")
                and models and all(model.get("execution_backend") == "cpu" for model in models)):
            self._failed("Thông tin máy hoặc danh sách model CPU không hợp lệ.")
            return
        self._preview = preview
        runtime = preview.get("runtime") or {}
        details = [runtime.get("platform"), runtime.get("cpu")]
        if runtime.get("ram_mb"):
            details.append(f"RAM {runtime['ram_mb']} MB")
        self.preview_label.setText(
            f"{preview.get('display_name') or preview['worker_id']} [{preview['worker_id']}]\n"
            + " · ".join(item for item in details if item)
            + "\nModel CPU: " + ", ".join(model["model_id"] for model in models)
        )
        self.preview_label.show()
        self.status.setText("Nếu đúng máy và model, bấm Cấp quyền cho máy.")
        self._sync_controls()

    def approve(self) -> None:
        if self._task is not None or self._preview is None:
            return
        preview, code = self._preview, self.code.text().strip().upper()
        self._clear_preview()
        self._start("Đang cấp quyền cho máy...", lambda: self.client.approve_pc_pairing(code, preview), self._approved)

    def _save_profile(self, device: dict) -> None:
        worker_id = device["worker_id"]
        saved = self._saved_profile(worker_id)
        profile = WorkerProfile(
            profile_id=worker_id, worker_id=worker_id, label=device.get("display_name") or worker_id,
            broker_url=self.broker_profile.broker_url, auth_env=self.broker_profile.auth_env,
            auth_token_file=self.broker_profile.auth_token_file, worker_kind="remote_pc",
            pool_enabled=saved.pool_enabled if saved else True,
        )
        self.store.upsert(profile)
        self.selected_profile_id = worker_id

    @Slot(object)
    def _approved(self, result: dict) -> None:
        self._task = None
        self.code.clear()
        try:
            self._save_profile(result)
        except (OSError, ValueError):
            self.refresh("Broker đã cấp quyền. Chọn máy trong danh sách để thử lưu hồ sơ lại.")
            return
        self.refresh("Đã cấp quyền. Máy sẽ xuất hiện ở trạng thái Sẵn sàng sau khi kết nối và nạp model.")

    def choose_device(self) -> None:
        device = self._selected()
        if self._task is not None or device is None or device.get("revoked"):
            return
        try:
            self._save_profile(device)
        except (OSError, ValueError):
            self.status.setText("Chưa lưu được hồ sơ máy trên Studio.")
            return
        self.accept()

    def control(self, action: str) -> None:
        device = self._selected()
        if self._task is not None or device is None or device.get("revoked"):
            return
        worker_id = device["worker_id"]
        desired = _CONTROL[action]
        if action == "stop" and not self._confirm(
            "Dừng xử lý trên máy CPU", f"Dừng nhận việc và hủy đoạn đang chạy trên máy {worker_id}?"
        ):
            return

        def request():
            result = self.client.control_pc_device(worker_id, action)
            if result.get("worker_id") != worker_id or result.get("desired_state") != desired:
                raise ValueError("Broker chưa xác nhận đúng yêu cầu điều khiển máy.")
            return result

        self._start("Đang gửi yêu cầu điều khiển...", request, self._controlled)

    @Slot(object)
    def _controlled(self, result: dict) -> None:
        self._task = None
        self._render_devices([
            item | result if item["worker_id"] == result["worker_id"] else item for item in self._devices
        ])
        action = _DESIRED[result["desired_state"]].lower()
        self.status.setText(f"Broker đã ghi yêu cầu {action}. Bấm Làm mới để xem máy đã nhận chưa.")

    def revoke(self) -> None:
        device = self._selected()
        if self._task is not None or device is None or device.get("revoked"):
            return
        worker_id = device["worker_id"]
        if not self._confirm("Ngắt quyền máy CPU", f"Ngắt quyền nhận việc của {worker_id}? Muốn dùng lại, bạn cần ghép máy lại."):
            return

        def request():
            result = self.client.revoke_pc_device(worker_id)
            if result.get("worker_id") != worker_id or result.get("status") != "revoked":
                raise ValueError("Broker chưa xác nhận đã ngắt quyền của máy này.")
            return result

        self._start("Đang ngắt quyền máy...", request, self._revoked)

    @Slot(object)
    def _revoked(self, result: dict) -> None:
        self._task = None
        worker_id = result["worker_id"]
        profile = next((item for item in self.store.load().profiles if item.profile_id == worker_id
                        and item.is_pc and item.broker_url == self.broker_profile.broker_url), None)
        notice = "Broker đã ngắt quyền máy CPU."
        if profile is not None:
            try:
                self.store.upsert(profile.model_copy(update={"enabled": False}))
            except OSError:
                notice += " Chưa cập nhật được hồ sơ trên Studio."
        if self.selected_profile_id == worker_id:
            self.selected_profile_id = ""
        self.refresh(notice)

    def _confirm(self, title: str, message: str) -> bool:
        return QMessageBox.question(
            self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    @Slot(str)
    def _failed(self, error: str) -> None:
        self._task = None
        self._clear_preview()
        notice, self._refresh_notice = self._refresh_notice, ""
        self.status.setText(
            f"{notice or 'Chưa xác nhận kết quả.'}\n{error}\nBấm Làm mới để xem trạng thái trên broker."
        )

    def reject(self) -> None:
        if self._task is None:
            super().reject()

    def closeEvent(self, event) -> None:
        if self._task is not None:
            event.ignore()
        else:
            super().closeEvent(event)
