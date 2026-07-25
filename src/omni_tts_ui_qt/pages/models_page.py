"""Model management page: catalog table, install/download/remove, setup checks."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.ui_presenters import labels, model_actions, model_groups
from omni_tts_core.ui_presenters.model_actions import build_action_policy
from omni_tts_core.ui_presenters.search import matches_search
from omni_tts_ui_qt.background import FunctionTask
from omni_tts_ui_qt.context import AppContext

_MODEL_COLUMNS = ["Tên model", "Provider", "Bắt buộc", "Trạng thái", "Dung lượng", "Đường dẫn"]
_SETUP_COLUMNS = ["Phạm vi", "Mục", "Trạng thái", "Hành động", "Chi tiết"]


class ModelsPage(QWidget):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._pool = QThreadPool.globalInstance()
        self._busy = False
        self._rows_by_id: dict[str, object] = {}
        self._policy = build_action_policy([])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Quản lý model")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addLayout(self._build_filters())

        self.model_table = QTableWidget(0, len(_MODEL_COLUMNS))
        self.model_table.setHorizontalHeaderLabels(_MODEL_COLUMNS)
        self.model_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Multi-select so one action can cover many models (Ctrl/Shift click).
        self.model_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.model_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.model_table, 2)
        self.summary = QLabel("")
        self.summary.setObjectName("hint")
        layout.addWidget(self.summary)

        layout.addLayout(self._build_buttons())

        layout.addWidget(QLabel("Kiểm tra máy và model đang chọn:"))
        self.setup_table = QTableWidget(0, len(_SETUP_COLUMNS))
        self.setup_table.setHorizontalHeaderLabels(_SETUP_COLUMNS)
        self.setup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.setup_table, 1)

        self.model_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.refresh()

    def _build_filters(self) -> QHBoxLayout:
        """Same provider-first classification the studio form uses."""
        row = QHBoxLayout()
        self.provider_filter = QComboBox()
        for label, provider_id in self.ctrl.model_provider_choices():
            self.provider_filter.addItem(label, provider_id)
        self.provider_filter.setToolTip(
            "Lọc bảng theo nhà cung cấp. Bảng luôn được nhóm theo nhà cung cấp rồi xếp theo tên."
        )
        self.provider_filter.currentIndexChanged.connect(self.refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên model…")
        self.search.textChanged.connect(self.refresh)
        row.addWidget(QLabel("Nhà cung cấp:"))
        row.addWidget(self.provider_filter)
        row.addWidget(self.search, 1)
        return row

    def _current_provider_filter(self) -> str:
        return str(self.provider_filter.currentData() or model_groups.ALL_PROVIDERS)

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._buttons = {}
        specs = [
            ("download", "Tải model", self._download),
            ("download_required", "Tải model bắt buộc", self._download_required),
            ("remove", "Gỡ model", self._remove),
            ("install_worker", "Cài worker", self._install_worker),
            ("install_gpu", "Cài GPU/CUDA", self._install_gpu),
            ("open", "Mở thư mục", self._open_storage),
            ("catalog", "Xem catalog", self._open_catalog),
            ("refresh", "Làm mới", self.refresh),
        ]
        for key, label, handler in specs:
            button = QPushButton(label)
            button.clicked.connect(handler)
            self._buttons[key] = button
            row.addWidget(button)
        row.addStretch()
        return row

    # --- Data refresh -------------------------------------------------------

    def refresh(self) -> None:
        selected = self._selected_model_ids()
        total = len(self.ctrl.all_models())
        models = self.ctrl.all_models(self._current_provider_filter())
        needle = self.search.text() if hasattr(self, "search") else ""
        models = [item for item in models if matches_search(item.display_name, needle)]
        self._rows_by_id = {item.model_id: item for item in models}
        self.model_table.setRowCount(len(models))
        for row, item in enumerate(models):
            values = [
                item.display_name,
                self.ctrl.provider_display_label(item.provider),
                "Có" if item.required else "",
                labels.model_status_label(item),
                labels.format_model_size(item),
                str(item.storage_path or item.local_path or ""),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.model_id)
                self.model_table.setItem(row, column, cell)
        self.summary.setText(f"Hiển thị {len(models)}/{total} model")
        self._restore_selection(selected)
        self._on_selection_changed()

    def _restore_selection(self, model_ids: list[str]) -> None:
        if not model_ids:
            return
        wanted = set(model_ids)
        self.model_table.clearSelection()
        for row in range(self.model_table.rowCount()):
            cell = self.model_table.item(row, 0)
            if cell and cell.data(Qt.ItemDataRole.UserRole) in wanted:
                self.model_table.selectRow(row)

    def _on_selection_changed(self) -> None:
        self._refresh_setup()
        self._update_action_states()

    def _update_action_states(self) -> None:
        """Enable each button only when it has something valid to do."""
        self._policy = self.ctrl.model_action_policy(self._selected_statuses())
        if self._busy:
            return
        for key, button in self._buttons.items():
            state = self._policy.state(key)
            button.setEnabled(state.enabled)
            button.setToolTip(state.tooltip)

    def _refresh_setup(self) -> None:
        model_id = self._selected_model_id()
        statuses = self.ctrl.setup_statuses(model_id)
        self.setup_table.setRowCount(len(statuses))
        for row, item in enumerate(statuses):
            for column, value in enumerate(labels.setup_status_values(item)):
                self.setup_table.setItem(row, column, QTableWidgetItem(value))

    def _selected_model_ids(self) -> list[str]:
        ids: list[str] = []
        for index in self.model_table.selectionModel().selectedRows():
            cell = self.model_table.item(index.row(), 0)
            model_id = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if model_id:
                ids.append(str(model_id))
        return ids

    def _selected_statuses(self) -> list:
        return [
            self._rows_by_id[model_id]
            for model_id in self._selected_model_ids()
            if model_id in self._rows_by_id
        ]

    def _selected_model_id(self) -> str | None:
        ids = self._selected_model_ids()
        return ids[0] if ids else None

    # --- Long-running actions ----------------------------------------------

    def _run_task(self, description: str, function) -> None:
        if self._busy:
            self.context.log("Đang có tác vụ model chạy, vui lòng đợi.")
            return
        self._set_busy(True)
        self.context.log(description)
        self.context.set_worker_status("processing", description)
        task = FunctionTask(function)
        task.signals.completed.connect(self._on_task_done)
        task.signals.failed.connect(self._on_task_failed)
        self._pool.start(task)

    def _on_task_done(self, message) -> None:
        self._set_busy(False)
        text = str(message) if message else "Hoàn tất."
        self.context.log(text)
        self.context.set_worker_status("ready", "Hoàn tất tác vụ model.")
        self.refresh()

    def _on_task_failed(self, message: str) -> None:
        self._set_busy(False)
        self.context.log(f"Lỗi: {message}")
        self.context.set_worker_status("error", "Tác vụ model thất bại.")
        QMessageBox.critical(self, "Lỗi", message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            for button in self._buttons.values():
                button.setEnabled(False)
        else:
            self._update_action_states()

    def _targets(self, action: str) -> tuple[str, ...]:
        return self._policy.state(action).targets

    def _name_of(self, model_id: str) -> str:
        item = self._rows_by_id.get(model_id)
        return item.display_name if item else model_id

    def _run_for_each(self, action: str, description: str, operation) -> None:
        """Run one operation over every target the policy selected."""
        targets = self._targets(action)
        if not targets:
            return
        names = ", ".join(self._name_of(model_id) for model_id in targets)

        def job() -> str:
            messages: list[str] = []
            for model_id in targets:
                messages.append(f"{self._name_of(model_id)}: {operation(model_id)}")
            return "\n".join(messages)

        self._run_task(f"{description} ({len(targets)}): {names}", job)

    def _download(self) -> None:
        self._run_for_each(model_actions.DOWNLOAD, "Đang tải model", self.ctrl.download_model)

    def _download_required(self) -> None:
        self._run_task("Đang tải các model bắt buộc còn thiếu…", self.ctrl.download_required_models)

    def _remove(self) -> None:
        targets = self._targets(model_actions.REMOVE)
        if not targets:
            return
        preview = "\n\n".join(self.ctrl.model_removal_preview(model_id) for model_id in targets)
        question = f"Gỡ {len(targets)} model?\n\n{preview}"
        if QMessageBox.question(self, "Gỡ model", question) != QMessageBox.StandardButton.Yes:
            return
        self._run_for_each(model_actions.REMOVE, "Đang gỡ model", self.ctrl.remove_model)

    def _install_worker(self) -> None:
        self._run_for_each(
            model_actions.INSTALL_WORKER, "Đang cài worker", self.ctrl.install_base_for_model
        )

    def _install_gpu(self) -> None:
        self._run_for_each(
            model_actions.INSTALL_GPU, "Đang cài GPU/CUDA", self.ctrl.install_gpu_for_model
        )

    def _open_storage(self) -> None:
        targets = self._targets(model_actions.OPEN_STORAGE)
        if not targets:
            return
        try:
            self.ctrl.open_model_storage(targets[0])
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))

    def _open_catalog(self) -> None:
        try:
            self.ctrl.open_model_catalog()
        except Exception as error:
            QMessageBox.critical(self, "Lỗi", str(error))
