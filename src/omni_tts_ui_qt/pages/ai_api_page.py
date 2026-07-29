from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from omni_tts_ui_qt.background import FunctionTask
from omni_tts_ui_qt.context import AppContext


class AiApiPage(QWidget):
    """Global AI-provider configuration, separate from all TTS providers."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.ctrl = context.controller
        self._tasks: set[FunctionTask] = set()
        self._busy = False
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Provider AI dùng để phân tích nội dung và lập Performance Plan. "
            "Đây không phải provider TTS; Higgs hoặc provider khác chỉ nhận kết "
            "quả qua authoring dialect tương ứng."
        )
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        layout.addWidget(intro)

        form = QFormLayout()
        self.provider = QComboBox()
        for label, provider_id in self.ctrl.authoring_ai_provider_choices():
            self.provider.addItem(label, provider_id)
        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.currentTextChanged.connect(self._sync_model_capability)
        self.base_url = QLineEdit()
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(5.0, 900.0)
        self.timeout.setSuffix(" giây")
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(0, 65536)
        self.max_tokens.setSingleStep(512)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.05)
        self.max_key_tries = QSpinBox()
        self.max_key_tries.setRange(1, 20)
        self.busy_retries = QSpinBox()
        self.busy_retries.setRange(0, 8)
        form.addRow("Provider AI:", self.provider)
        form.addRow("Model:", self.model)
        form.addRow("Base URL:", self.base_url)
        form.addRow("Request timeout:", self.timeout)
        form.addRow("Max output tokens:", self.max_tokens)
        form.addRow("Temperature:", self.temperature)
        form.addRow("Số key tối đa mỗi request:", self.max_key_tries)
        form.addRow("Retry khi server bận:", self.busy_retries)
        layout.addLayout(form)

        provider_actions = QHBoxLayout()
        self.save_button = QPushButton("Lưu cấu hình")
        self.save_button.setObjectName("primaryButton")
        self.test_button = QPushButton("Kiểm tra kết nối")
        self.refresh_models_button = QPushButton("Lấy danh sách model")
        self.import_button = QPushButton("Nhập key pool từ JSON")
        provider_actions.addWidget(self.save_button)
        provider_actions.addWidget(self.test_button)
        provider_actions.addWidget(self.refresh_models_button)
        provider_actions.addWidget(self.import_button)
        provider_actions.addStretch()
        layout.addLayout(provider_actions)

        self.pool_summary = QLabel("")
        self.pool_summary.setObjectName("hint")
        layout.addWidget(self.pool_summary)
        self.keys = QTableWidget()
        self.keys.setColumnCount(3)
        self.keys.setHorizontalHeaderLabels(["Tên key", "Key đã ẩn", "Trạng thái"])
        self.keys.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.keys.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.keys.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.keys.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.keys.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.keys, 1)

        key_actions = QHBoxLayout()
        self.add_key_button = QPushButton("+ Thêm key")
        self.replace_key_button = QPushButton("Sửa / thay key")
        self.reset_key_button = QPushButton("Kích hoạt lại")
        self.remove_key_button = QPushButton("Xóa")
        key_actions.addWidget(self.add_key_button)
        key_actions.addWidget(self.replace_key_button)
        key_actions.addWidget(self.reset_key_button)
        key_actions.addWidget(self.remove_key_button)
        key_actions.addStretch()
        layout.addLayout(key_actions)

        self.save_button.clicked.connect(self._save)
        self.test_button.clicked.connect(self._test)
        self.refresh_models_button.clicked.connect(self._refresh_models)
        self.import_button.clicked.connect(self._import)
        self.add_key_button.clicked.connect(self._add_key)
        self.replace_key_button.clicked.connect(self._replace_key)
        self.reset_key_button.clicked.connect(self._reset_key)
        self.remove_key_button.clicked.connect(self._remove_key)
        self.keys.itemSelectionChanged.connect(self._sync_key_actions)

    def _load(self) -> None:
        settings = self.ctrl.authoring_ai_settings()
        provider_index = self.provider.findData(settings.provider_id)
        if provider_index >= 0:
            self.provider.setCurrentIndex(provider_index)
        self.model.clear()
        for model in self.ctrl.authoring_model_choices(settings.provider_id):
            self.model.addItem(model)
        self.model.setCurrentText(settings.model)
        self.base_url.setText(settings.base_url)
        self.timeout.setValue(settings.timeout_seconds)
        self.max_tokens.setValue(settings.max_output_tokens)
        self.temperature.setValue(settings.temperature)
        self.max_key_tries.setValue(settings.max_key_tries)
        self.busy_retries.setValue(settings.max_busy_retries)
        self._refresh_keys()
        self._sync_model_capability()

    def _settings_payload(self) -> dict:
        return {
            "provider_id": str(self.provider.currentData()),
            "model": self.model.currentText().strip(),
            "base_url": self.base_url.text().strip(),
            "timeout_seconds": self.timeout.value(),
            "max_output_tokens": self.max_tokens.value(),
            "temperature": self.temperature.value(),
            "max_key_tries": self.max_key_tries.value(),
            "max_busy_retries": self.busy_retries.value(),
        }

    def _save(self) -> None:
        try:
            settings = self.ctrl.save_authoring_ai_settings(
                self._settings_payload()
            )
        except Exception as error:
            QMessageBox.warning(self, "Không lưu được", str(error))
            return
        self.context.log(
            f"Đã lưu AI provider: {settings.provider_id}/{settings.model}"
        )
        QMessageBox.information(self, "AI / API", "Đã lưu cấu hình.")

    def _sync_model_capability(self, *_args) -> None:
        supported = self.ctrl.authoring_model_supports_temperature(
            self.model.currentText(),
            str(self.provider.currentData()),
        )
        self.temperature.setEnabled(supported)
        self.temperature.setToolTip(
            "Độ ngẫu nhiên của kết quả."
            if supported
            else "Model này không nhận temperature; core tự bỏ tham số."
        )

    def _on_provider_changed(self) -> None:
        current = self.model.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(
            self.ctrl.authoring_model_choices(str(self.provider.currentData()))
        )
        if current:
            self.model.setCurrentText(current)
        self.model.blockSignals(False)
        self._refresh_keys()
        self._sync_model_capability()

    def _refresh_keys(self) -> None:
        provider_id = str(self.provider.currentData())
        keys = self.ctrl.authoring_keys(provider_id)
        self.keys.setRowCount(len(keys))
        for row, item in enumerate(keys):
            name_item = QTableWidgetItem(item["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, item["name"])
            self.keys.setItem(row, 0, name_item)
            self.keys.setItem(row, 1, QTableWidgetItem(item["masked"]))
            status = item["status"]
            marker = "✓" if status == "active" else "⚠"
            self.keys.setItem(row, 2, QTableWidgetItem(f"{marker} {status}"))
        self.pool_summary.setText(
            f"{self.provider.currentText()}: "
            f"{self.ctrl.authoring_active_key_count(provider_id)}/{len(keys)} key active. "
            "Key chỉ nằm trong file runtime cục bộ và không được ghi vào log."
        )
        self._sync_key_actions()

    def _selected_key_name(self) -> str:
        row = self.keys.currentRow()
        if row < 0:
            return ""
        item = self.keys.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def _sync_key_actions(self) -> None:
        enabled = bool(self._selected_key_name())
        self.replace_key_button.setEnabled(enabled)
        self.reset_key_button.setEnabled(enabled)
        self.remove_key_button.setEnabled(enabled)

    def _add_key(self) -> None:
        dialog = _KeyDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, value = dialog.values()
        if not self.ctrl.add_authoring_key(
            name, value, str(self.provider.currentData())
        ):
            QMessageBox.warning(
                self,
                "Không thêm được",
                "Tên hoặc giá trị key bị trùng, hoặc đang để trống.",
            )
        self._refresh_keys()

    def _replace_key(self) -> None:
        old_name = self._selected_key_name()
        if not old_name:
            return
        dialog = _KeyDialog(self, name=old_name)
        dialog.setWindowTitle("Sửa tên và thay giá trị key")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, value = dialog.values()
        if not self.ctrl.update_authoring_key(
            old_name, name, value, str(self.provider.currentData())
        ):
            QMessageBox.warning(
                self,
                "Không cập nhật được",
                "Key mới trống hoặc trùng một key khác.",
            )
        self._refresh_keys()

    def _reset_key(self) -> None:
        name = self._selected_key_name()
        if name:
            self.ctrl.reset_authoring_key(
                name, str(self.provider.currentData())
            )
            self._refresh_keys()

    def _remove_key(self) -> None:
        name = self._selected_key_name()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "Xóa API key",
            f"Xóa key '{name}' khỏi pool cục bộ?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctrl.remove_authoring_key(
                name, str(self.provider.currentData())
            )
            self._refresh_keys()

    def _import(self) -> None:
        suggested = Path(r"D:\_coder\rewrite-truyen-dai\data\key_pool.json")
        initial = str(suggested.parent if suggested.exists() else Path.cwd())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Nhập Gemini key pool",
            initial,
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            report = self.ctrl.import_authoring_keys(
                Path(path), str(self.provider.currentData())
            )
        except Exception as error:
            QMessageBox.warning(self, "Không nhập được key", str(error))
            return
        self._refresh_keys()
        QMessageBox.information(
            self,
            "Đã nhập key",
            f"Nguồn: {report.source_count}\n"
            f"Thêm mới: {report.added}\n"
            f"Trùng: {report.duplicates}\n"
            f"Bỏ qua: {report.skipped}",
        )

    def _test(self) -> None:
        self.ctrl.save_authoring_ai_settings(self._settings_payload())
        self._run_task(
            self.ctrl.test_authoring_connection,
            lambda message: QMessageBox.information(
                self, "Kết nối thành công", str(message)
            ),
        )

    def _refresh_models(self) -> None:
        self.ctrl.save_authoring_ai_settings(self._settings_payload())

        def on_success(models) -> None:
            current = self.model.currentText()
            self.model.clear()
            self.model.addItems(models)
            if current:
                self.model.setCurrentText(current)
            QMessageBox.information(
                self,
                "Danh sách model",
                f"Đã lấy {len(models)} model Gemini từ API.",
            )

        self._run_task(self.ctrl.refresh_authoring_models, on_success)

    def _run_task(self, function, on_success) -> None:
        task = FunctionTask(function)
        self._tasks.add(task)
        self._set_busy(True)

        def completed(result) -> None:
            self._tasks.discard(task)
            self._set_busy(bool(self._tasks))
            on_success(result)

        def failed(message: str) -> None:
            self._tasks.discard(task)
            self._set_busy(bool(self._tasks))
            self._refresh_keys()
            QMessageBox.warning(self, "AI / API", message)

        task.signals.completed.connect(completed)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.test_button.setEnabled(not busy)
        self.refresh_models_button.setEnabled(not busy)
        self.test_button.setText("Đang xử lý…" if busy else "Kiểm tra kết nối")

    def is_busy(self) -> bool:
        return self._busy


class _KeyDialog(QDialog):
    def __init__(self, parent=None, *, name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemini API key")
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.value_edit = QLineEdit()
        self.value_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.value_edit.setPlaceholderText("Dán API key mới")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow("Tên:", self.name_edit)
        form.addRow("API key:", self.value_edit)
        form.addRow(buttons)

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.value_edit.text().strip()

    def accept(self) -> None:
        if not all(self.values()):
            QMessageBox.warning(self, "Thiếu dữ liệu", "Tên và API key đều bắt buộc.")
            return
        super().accept()
