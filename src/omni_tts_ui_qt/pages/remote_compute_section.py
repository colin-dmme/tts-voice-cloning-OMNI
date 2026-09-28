from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_core.remote_compute.client import BrokerClient
from omni_tts_core.remote_compute.models import BrokerConnectionOptions
from omni_tts_core.remote_compute.profiles import WorkerProfileStore
from omni_tts_ui_qt.background import FunctionTask


_POLICIES = (
    ("Chỉ worker đã chọn", "selected_only"),
    ("Hỏi trước khi chuyển", "ask_before_switch"),
    ("Tự chuyển khi có lỗi", "automatic_failover"),
)


class RemoteComputeGroup(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.store = WorkerProfileStore(
            PROJECT_ROOT / "config" / "remote_compute_workers.json"
        )
        self._loading = False
        self._task: FunctionTask | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.profile = QComboBox()
        self.policy = QComboBox()
        for label, value in _POLICIES:
            self.policy.addItem(label, value)
        form.addRow("Worker ưu tiên:", self.profile)
        form.addRow("Khi worker lỗi:", self.policy)
        layout.addLayout(form)

        self.status = QLabel("Chưa kiểm tra trạng thái worker.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.check_button = QPushButton("Kiểm tra kết nối")
        self.manage_button = QPushButton("Quản lý worker")
        actions.addWidget(self.check_button)
        actions.addWidget(self.manage_button)
        layout.addLayout(actions)

        self.profile.currentIndexChanged.connect(self._save_selection)
        self.policy.currentIndexChanged.connect(self._save_selection)
        self.check_button.clicked.connect(self.check_connections)
        self.manage_button.clicked.connect(self.manage_profiles)
        self.reload()

    def reload(self) -> None:
        document = self.store.load()
        self._loading = True
        try:
            self.profile.clear()
            for item in document.profiles:
                suffix = "" if item.enabled else " (đã tắt)"
                self.profile.addItem(f"{item.label}{suffix}", item.profile_id)
            selected = self.profile.findData(document.selection.selected_profile_id)
            if selected >= 0:
                self.profile.setCurrentIndex(selected)
            policy = self.policy.findData(document.selection.switch_policy)
            if policy >= 0:
                self.policy.setCurrentIndex(policy)
            enabled = bool(document.profiles)
            self.profile.setEnabled(enabled)
            self.policy.setEnabled(enabled)
            self.check_button.setEnabled(enabled)
        finally:
            self._loading = False

    def _save_selection(self, *_args) -> None:
        if self._loading:
            return
        document = self.store.load()
        document.selection.selected_profile_id = str(
            self.profile.currentData() or ""
        )
        document.selection.switch_policy = str(
            self.policy.currentData() or "selected_only"
        )
        self.store.save(document)
        self.changed.emit()

    def check_connections(self) -> None:
        self.check_button.setEnabled(False)
        self.status.setText("Đang hỏi broker về 3 worker...")
        task = FunctionTask(self._probe)
        self._task = task
        task.signals.completed.connect(self._probe_finished)
        task.signals.failed.connect(self._probe_failed)
        QThreadPool.globalInstance().start(task)

    def _probe(self) -> list[tuple[str, bool, str]]:
        document = self.store.load()
        results: list[tuple[str, bool, str]] = []
        for profile in document.profiles:
            client = BrokerClient(
                BrokerConnectionOptions(
                    base_url=profile.broker_url,
                    auth_env=profile.auth_env,
                    auth_token_file=profile.auth_token_file,
                    request_timeout_seconds=20.0,
                    max_retries=0,
                )
            )
            workers = client.list_workers()
            worker = next(
                (
                    item
                    for item in workers
                    if item.capabilities.worker_id == profile.worker_id
                ),
                None,
            )
            if worker is None:
                results.append((profile.label, False, "chưa chạy notebook"))
                continue
            try:
                seen = datetime.fromisoformat(worker.last_seen_at)
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                age = max(0.0, (datetime.now(timezone.utc) - seen).total_seconds())
            except ValueError:
                age = 999999.0
            online = age <= 120.0
            detail = "online" if online else f"mất heartbeat {int(age)} giây"
            results.append((profile.label, online, detail))
        return results

    def _probe_finished(self, results: list[tuple[str, bool, str]]) -> None:
        self._task = None
        self.check_button.setEnabled(True)
        self.status.setText(
            "\n".join(
                f"{'●' if online else '○'} {label}: {detail}"
                for label, online, detail in results
            )
        )

    def _probe_failed(self, error: str) -> None:
        self._task = None
        self.check_button.setEnabled(True)
        self.status.setText(f"Không kiểm tra được broker: {error}")

    def manage_profiles(self) -> None:
        document = self.store.load()
        dialog = QDialog(self)
        dialog.setWindowTitle("Quản lý worker Colab")
        dialog.resize(460, 330)
        layout = QVBoxLayout(dialog)
        note = QLabel(
            "Đánh dấu worker được phép dùng. Thứ tự từ trên xuống là thứ tự "
            "dự phòng khi có lỗi."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        workers = QListWidget()
        for profile in document.profiles:
            item = QListWidgetItem(f"{profile.label}  [{profile.worker_id}]")
            item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if profile.enabled else Qt.CheckState.Unchecked
            )
            workers.addItem(item)
        layout.addWidget(workers, 1)
        order = QHBoxLayout()
        up = QPushButton("Lên")
        down = QPushButton("Xuống")
        order.addWidget(up)
        order.addWidget(down)
        order.addStretch()
        layout.addLayout(order)

        def move(delta: int) -> None:
            row = workers.currentRow()
            target = row + delta
            if row < 0 or target < 0 or target >= workers.count():
                return
            item = workers.takeItem(row)
            workers.insertItem(target, item)
            workers.setCurrentRow(target)

        up.clicked.connect(lambda: move(-1))
        down.clicked.connect(lambda: move(1))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        by_id = {profile.profile_id: profile for profile in document.profiles}
        ordered_ids: list[str] = []
        for row in range(workers.count()):
            item = workers.item(row)
            profile_id = str(item.data(Qt.ItemDataRole.UserRole))
            by_id[profile_id].enabled = item.checkState() == Qt.CheckState.Checked
            ordered_ids.append(profile_id)
        document.profiles = [by_id[profile_id] for profile_id in ordered_ids]
        if not any(item.enabled for item in document.profiles):
            QMessageBox.warning(dialog, "Thiếu worker", "Phải bật ít nhất một worker.")
            return
        selected = next(
            (
                item
                for item in document.profiles
                if item.profile_id == document.selection.selected_profile_id and item.enabled
            ),
            None,
        )
        if selected is None:
            document.selection.selected_profile_id = next(
                item.profile_id for item in document.profiles if item.enabled
            )
        self.store.save(document)
        self.reload()
        self.changed.emit()
