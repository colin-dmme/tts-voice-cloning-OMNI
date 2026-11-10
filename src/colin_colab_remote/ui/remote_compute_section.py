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
from colin_colab_remote.broker.client import BrokerClient
from colin_colab_remote.broker.models import BrokerConnectionOptions
from colin_colab_remote.broker.profiles import WorkerProfileStore
from omni_tts_ui_qt.background import FunctionTask
from .colab_pairing_dialog import ColabPairingDialog, pairing_client
from .broker_control import BrokerControlWidget
from omni_tts_core.runtime_devices import REMOTE_CPU_CHOICE


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
        self._model_id = "zerotts_202m_official"
        self._choice = "auto"
        self._allow_colab = True
        self._pc_profile_id = ""
        self._probe_target: tuple[str, str, str] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.form = QFormLayout()
        self.profile = QComboBox()
        self.pc_profile = QComboBox()
        self.policy = QComboBox()
        for label, value in _POLICIES:
            self.policy.addItem(label, value)
        self.form.addRow("Máy xử lý:", self.pc_profile)
        self.form.addRow("Worker Colab ưu tiên:", self.profile)
        self.form.addRow("Khi worker lỗi:", self.policy)
        layout.addLayout(self.form)

        self.status = QLabel("Chưa kiểm tra trạng thái worker.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.check_button = QPushButton("Kiểm tra kết nối")
        self.manage_button = QPushButton("Quản lý worker Colab")
        actions.addWidget(self.check_button)
        actions.addWidget(self.manage_button)
        layout.addLayout(actions)

        pairing_actions = QHBoxLayout()
        self.pair_button = QPushButton("Kết nối Colab bằng mã")
        self.revoke_button = QPushButton("Ngắt quyền Colab")
        self.pair_button.setToolTip("Mở notebook và ghép nối bằng mã ngắn; không cần nhập Secrets.")
        self.revoke_button.setToolTip("Thu hồi phiên ghép nối của worker đang chọn; không xóa tài khoản hay Secrets cũ.")
        pairing_actions.addWidget(self.pair_button)
        pairing_actions.addWidget(self.revoke_button)
        layout.addLayout(pairing_actions)

        self.broker_button = QPushButton("Trạng thái / Bật tắt broker nền")
        self.broker_button.clicked.connect(self.manage_broker)
        layout.addWidget(self.broker_button)

        self.managed_button = QPushButton("Quản lý Colab tự động")
        self.managed_button.clicked.connect(self.manage_colab_auto)
        layout.addWidget(self.managed_button)

        self.profile.currentIndexChanged.connect(self._save_selection)
        self.pc_profile.currentIndexChanged.connect(self._save_pc_selection)
        self.policy.currentIndexChanged.connect(self._save_selection)
        self.check_button.clicked.connect(self.check_connections)
        self.manage_button.clicked.connect(self.manage_profiles)
        self.pair_button.clicked.connect(self.pair_colab)
        self.revoke_button.clicked.connect(self.revoke_colab)
        self.reload()

    def set_model_id(self, model_id: str) -> None:
        if model_id != self._model_id:
            self._model_id = model_id
            self._reset_status()

    @property
    def pc_profile_id(self) -> str:
        return self._pc_profile_id

    def set_pc_profile_id(self, profile_id: str | None) -> None:
        self._pc_profile_id = str(profile_id or "")
        self.reload()
        self._reset_status()

    def set_runtime_choice(self, choice: str, *, allow_colab: bool) -> None:
        changed = choice != self._choice or allow_colab != self._allow_colab
        self._choice, self._allow_colab = choice, allow_colab
        self._sync_controls()
        if changed:
            self._reset_status()

    def _reset_status(self) -> None:
        self.status.setText("Chưa kiểm tra worker cho model đang chọn.")

    def _sync_controls(self) -> None:
        pc = self._choice == REMOTE_CPU_CHOICE
        colab = self._allow_colab and not pc
        self.form.setRowVisible(self.pc_profile, pc)
        self.form.setRowVisible(self.profile, colab)
        self.form.setRowVisible(self.policy, colab)
        self.status.setVisible(colab)
        self.check_button.setVisible(colab)
        self.manage_button.setVisible(colab)
        self.pair_button.setVisible(colab)
        self.revoke_button.setVisible(colab)
        self.managed_button.setVisible(colab)
        self.broker_button.setVisible(colab)
        idle = self._task is None
        colab_selected = self._selected_profile() is not None
        self.check_button.setEnabled(idle and (self._selected_pc_profile() is not None if pc else colab_selected))
        self.pair_button.setEnabled(idle and colab_selected)
        self.revoke_button.setEnabled(idle and colab_selected)

    def reload(self) -> None:
        document = self.store.load()
        self._loading = True
        try:
            self.profile.clear()
            self.pc_profile.clear()
            self.pc_profile.addItem("Tự chia tải", "")
            self.pc_profile.setToolTip("Bật hoặc bỏ máy tham gia trong tab Máy CPU bên trái.")
            for item in document.profiles:
                if item.is_pc:
                    if item.enabled:
                        self.pc_profile.addItem(item.label, item.profile_id)
                else:
                    suffix = "" if item.enabled else " (đã tắt)"
                    self.profile.addItem(f"{item.label}{suffix}", item.profile_id)
            pc_index = self.pc_profile.findData(self._pc_profile_id)
            if pc_index < 0:
                self.pc_profile.addItem(f"Máy không khả dụng ({self._pc_profile_id})", self._pc_profile_id)
                pc_index = self.pc_profile.count() - 1
            self.pc_profile.setCurrentIndex(pc_index)
            selected = self.profile.findData(document.selection.selected_profile_id)
            if selected >= 0:
                self.profile.setCurrentIndex(selected)
            policy = self.policy.findData(document.selection.switch_policy)
            if policy >= 0:
                self.policy.setCurrentIndex(policy)
            enabled = self.profile.count() > 0
            self.profile.setEnabled(enabled)
            self.policy.setEnabled(enabled)
        finally:
            self._loading = False
        self._sync_controls()
        if self._choice == REMOTE_CPU_CHOICE and self._selected_pc_profile() is None:
            self._reset_status()

    def _save_pc_selection(self, *_args) -> None:
        if self._loading:
            return
        self._pc_profile_id = str(self.pc_profile.currentData() or "")
        self._sync_controls()
        self._reset_status()
        self.changed.emit()

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
        self._sync_controls()
        self.changed.emit()

    def check_connections(self) -> None:
        if self._task is not None:
            return
        pc = self._choice == REMOTE_CPU_CHOICE
        if pc:
            selected = self._selected_pc_profile()
            if selected is None:
                return
            profiles = [selected]
        else:
            profiles = [item for item in self.store.load().profiles if not item.is_pc]
        model_id = self._model_id
        self._probe_target = self._target_key()
        self.status.setText("Đang hỏi broker về worker và model đang chạy...")
        task = FunctionTask(lambda: self._probe(profiles, model_id, pc=pc))
        self._task = task
        self._sync_controls()
        task.signals.completed.connect(self._probe_finished)
        task.signals.failed.connect(self._probe_failed)
        QThreadPool.globalInstance().start(task)

    def _target_key(self) -> tuple[str, str, str]:
        profile_id = self._pc_profile_id if self._choice == REMOTE_CPU_CHOICE else self.profile.currentData()
        return self._choice, self._model_id, str(profile_id or "")

    @staticmethod
    def _probe(profiles, model_id: str, *, pc: bool) -> list[tuple[str, bool, str]]:
        results: list[tuple[str, bool, str]] = []
        for profile in profiles:
            client = BrokerClient(
                BrokerConnectionOptions(
                    base_url=profile.broker_url,
                    auth_env=profile.auth_env,
                    auth_token_file=profile.auth_token_file,
                    request_timeout_seconds=20.0,
                    max_retries=0,
                )
            )
            if pc:
                device = next((item for item in client.list_pc_devices() if item.get("worker_id") == profile.worker_id), None)
                if device is None or device.get("revoked"):
                    results.append((profile.label, False, "máy chưa được ghép nối"))
                    continue
                if model_id not in (device.get("allowed_models") or []):
                    results.append((profile.label, False, "máy chưa được duyệt cho model này"))
                    continue
                if device.get("desired_state") != "running":
                    results.append((profile.label, False, "máy đang tạm ngừng nhận việc"))
                    continue
                if device.get("observed_state") not in {"idle", "busy"}:
                    results.append((profile.label, False, "máy chưa báo sẵn sàng"))
                    continue
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
                results.append((profile.label, False, "worker chưa kết nối"))
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
            capability = next((item for item in worker.capabilities.models if item.model_id == model_id), None)
            if online and capability is None:
                online = False
                detail = "online nhưng chưa có model này"
            elif online and capability is not None:
                if pc and capability.execution_backend != "cpu":
                    online = False
                    detail = "model không công bố backend CPU"
                elif model_id == "vieneu_v3_turbo" and not (capability.supports_profile_clone and capability.supports_batch):
                    online = False
                    detail = "worker chưa hỗ trợ clone/batch cho VieNeu v3"
                else:
                    detail += f" · {capability.execution_backend.upper()}"
                    if capability.supports_profile_clone:
                        detail += " · preset + clone"
            results.append((profile.label, online, detail))
        return results

    def _probe_finished(self, results: list[tuple[str, bool, str]]) -> None:
        self._task = None
        self._sync_controls()
        if self._probe_target != self._target_key():
            return
        self.status.setText(
            "\n".join(
                f"{'●' if online else '○'} {label}: {detail}"
                for label, online, detail in results
            )
        )

    def _probe_failed(self, error: str) -> None:
        self._task = None
        self._sync_controls()
        if self._probe_target == self._target_key():
            self.status.setText(f"Không kiểm tra được broker: {error}")

    def _selected_profile(self):
        return next((item for item in self.store.load().profiles
                     if item.profile_id == self.profile.currentData() and item.enabled and not item.is_pc), None)

    def _selected_pc_profile(self):
        return next((item for item in self.store.load().profiles
                     if item.profile_id == self._pc_profile_id and item.enabled and item.is_pc), None)

    def manage_broker(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Broker trên PC — Trạng thái và chạy nền")
        dialog.resize(650, 350)
        layout = QVBoxLayout(dialog)
        control = BrokerControlWidget(dialog)
        layout.addWidget(control)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        control.timer.stop()

    def manage_colab_auto(self) -> None:
        from .managed_dialog import ManagedColabDialog

        dialog = ManagedColabDialog(self)
        dialog.exec()

    def pair_colab(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.status.setText("Chọn một worker đang bật trước khi ghép nối.")
            return
        dialog = ColabPairingDialog(profile, self._model_id, self)
        dialog.exec()

    def revoke_colab(self) -> None:
        profile = self._selected_profile()
        if profile is None or self._task is not None:
            return
        answer = QMessageBox.question(
            self, "Ngắt quyền worker Colab?",
            f"Ngắt các phiên ghép nối của {profile.label} [{profile.worker_id}]?\n"
            "Job đang chạy có thể bị gián đoạn. Notebook dùng Secrets cũ không bị thu hồi bởi nút này.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.revoke_button.setEnabled(False)
        self.check_button.setEnabled(False)
        client = pairing_client(profile)
        task = FunctionTask(lambda: client.revoke_pairing(profile.worker_id))
        self._task = task
        task.signals.completed.connect(self._revoked)
        task.signals.failed.connect(self._revoke_failed)
        QThreadPool.globalInstance().start(task)

    def _revoked(self, result) -> None:
        self._task = None
        self._sync_controls()
        self.status.setText(f"Đã ngắt {result.get('sessions', 0)} phiên ghép nối của {result.get('worker_id', '')}. Muốn dùng lại, chạy notebook lấy mã mới.")

    def _revoke_failed(self, error: str) -> None:
        self._task = None
        self._sync_controls()
        self.status.setText(f"Không ngắt được quyền Colab: {error}")

    def manage_profiles(self) -> None:
        document = self.store.load()
        colab_profiles = [profile for profile in document.profiles if not profile.is_pc]
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
        for profile in colab_profiles:
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

        by_id = {profile.profile_id: profile for profile in colab_profiles}
        ordered_ids: list[str] = []
        for row in range(workers.count()):
            item = workers.item(row)
            profile_id = str(item.data(Qt.ItemDataRole.UserRole))
            by_id[profile_id].enabled = item.checkState() == Qt.CheckState.Checked
            ordered_ids.append(profile_id)
        colab_profiles = [by_id[profile_id] for profile_id in ordered_ids]
        if not any(item.enabled for item in colab_profiles):
            QMessageBox.warning(dialog, "Thiếu worker", "Phải bật ít nhất một worker.")
            return
        selected = next(
            (
                item
                for item in colab_profiles
                if item.profile_id == document.selection.selected_profile_id and item.enabled
            ),
            None,
        )
        if selected is None:
            document.selection.selected_profile_id = next(
                item.profile_id for item in colab_profiles if item.enabled
            )
        document.profiles = colab_profiles + [profile for profile in document.profiles if profile.is_pc]
        self.store.save(document)
        self.reload()
        self.changed.emit()
