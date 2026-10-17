from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from omni_tts_core.remote_compute.local_broker import LocalBrokerManager, LocalBrokerStatus
from omni_tts_ui_qt.background import FunctionTask


class BrokerControlWidget(QWidget):
    def __init__(self, parent=None, *, manager: LocalBrokerManager | None = None, auto_refresh: bool = True):
        super().__init__(parent)
        self.manager = manager or LocalBrokerManager()
        self._task: FunctionTask | None = None
        self._last: LocalBrokerStatus | None = None
        self._public: bool | None = None
        self._mutation = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("Broker trên PC: chưa kiểm tra.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Bật chạy nền")
        self.stop_button = QPushButton("Tắt chạy nền")
        self.refresh_button = QPushButton("Làm mới trạng thái")
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.refresh_button)
        layout.addLayout(actions)
        self.logs_button = QPushButton("Mở thư mục log")
        layout.addWidget(self.logs_button)
        self.note = QLabel(
            "Đóng Studio/cửa sổ quản lý không tắt broker. Tắt chạy nền sẽ ngắt kết nối TẤT CẢ worker Colab "
            "và giữ tắt cả lần đăng nhập Windows sau, đến khi bấm Bật. Model chạy ngay trên PC không bị ảnh hưởng."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.start_button.clicked.connect(self.start_broker)
        self.stop_button.clicked.connect(self.stop_broker)
        self.refresh_button.clicked.connect(lambda: self.refresh(check_public=True))
        self.logs_button.clicked.connect(self.open_logs)
        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.refresh)
        if auto_refresh:
            self.timer.start()
            QTimer.singleShot(0, self.refresh)

    def _run(self, function, *, mutation: bool = False):
        if self._task is not None:
            return
        self._mutation = mutation
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        task = FunctionTask(function)
        self._task = task
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def refresh(self, *, check_public: bool = False):
        self._run(lambda: self.manager.status(check_public=check_public))

    def start_broker(self):
        if self._task is None:
            self.status_label.setText("Đang bật broker nền, chờ Windows và dịch vụ khởi động...")
            self._public = None
            self._run(self.manager.start, mutation=True)

    def stop_broker(self):
        if self._task is not None:
            return
        answer = QMessageBox.question(
            self, "Tắt broker chạy nền?",
            "Tắt broker sẽ ngắt TẤT CẢ worker Colab và có thể gián đoạn audio đang xử lý.\n"
            "Windows sẽ không tự bật broker ở lần đăng nhập sau cho đến khi bạn bấm Bật chạy nền.\n\n"
            "Không xóa job, audio, model hoặc khóa. Muốn dừng GPU Google, bạn còn cần dừng runtime trên Colab.\n\nTắt ngay?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.status_label.setText("Đang dừng broker và tunnel; kiểm tra đến khi dừng thật...")
            self._public = None
            self._run(self.manager.stop, mutation=True)

    def _completed(self, result: LocalBrokerStatus):
        self._task = None
        self._mutation = False
        self._last = result
        if result.public_healthy is not None:
            self._public = result.public_healthy
        if not result.local_healthy:
            self._public = None
        if result.local_healthy:
            local = f"ĐANG CHẠY · port {result.local_port or '—'}"
        elif not result.desired_running:
            local = "ĐÃ TẮT theo yêu cầu"
        elif result.task_state == "Running":
            local = "ĐANG KHỞI ĐỘNG / chưa healthy — kiểm tra log"
        else:
            local = "CHƯA CHẠY"
        internet = "chưa kiểm tra (bấm Làm mới)" if self._public is None else ("kết nối tốt" if self._public else "chưa kết nối được; PC có thể vẫn chạy")
        lines = [f"Broker trên PC: {local}", f"HTTPS/Colab: {internet}",
                 f"Tự chạy khi đăng nhập Windows: {'BẬT' if result.auto_start and result.desired_running else 'TẮT'}"]
        if result.running_jobs is not None:
            lines.append(f"Job đang xử lý: {result.running_jobs} · đang chờ: {result.queued_jobs or 0}")
        if result.local_healthy and not result.hidden_launcher:
            lines.append("Launcher cũ: cần cài bản chạy nền pythonw để không hiện cửa sổ.")
        self.status_label.setText("\n".join(lines))
        self.start_button.setEnabled(not result.local_healthy or not result.desired_running)
        self.stop_button.setEnabled(result.local_healthy or result.task_state == "Running")
        self.refresh_button.setEnabled(True)

    def _failed(self, error: str):
        self._task = None
        self._mutation = False
        self.status_label.setText(f"Không xác nhận được trạng thái broker: {error}")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.refresh_button.setEnabled(True)

    def open_logs(self):
        directory = self.manager.data_dir / "logs"
        if directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        else:
            self.status_label.setText(f"Chưa có thư mục log: {directory}")
