"""User-driven device pairing; all broker calls run off the GUI thread."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from omni_tts_core.remote_compute.client import BrokerClient
from omni_tts_core.remote_compute.models import BrokerConnectionOptions, PairingPreview, WorkerProfile
from omni_tts_ui_qt.background import FunctionTask


def pairing_client(profile: WorkerProfile) -> BrokerClient:
    return BrokerClient(BrokerConnectionOptions(
        base_url=profile.broker_url, auth_env=profile.auth_env,
        auth_token_file=profile.auth_token_file, request_timeout_seconds=20, max_retries=0,
    ))


def notebook_url(worker_id: str) -> str:
    if worker_id not in {f"google-pro-{n}" for n in range(1, 4)}:
        raise ValueError("Chưa có notebook ghép nối cho worker này")
    return ("https://colab.research.google.com/github/colin-dmme/tts-voice-cloning-OMNI/"
            f"blob/main/colab/Colin-TTS-Pairing-{worker_id}.ipynb")


class ColabPairingDialog(QDialog):
    def __init__(self, profile: WorkerProfile, model_id: str, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.provider = "vieneu_v3" if model_id == "vieneu_v3_turbo" else "zerotts"
        self.client = pairing_client(profile)
        self.preview: PairingPreview | None = None
        self._task: FunctionTask | None = None
        self._busy = False
        self.setWindowTitle("Kết nối Colab bằng mã — không cần Secrets")
        self.resize(540, 410)
        layout = QVBoxLayout(self)
        title = QLabel(f"Worker đã chọn: {profile.label} [{profile.worker_id}]")
        title.setWordWrap(True)
        layout.addWidget(title)
        note = QLabel(
            "1. Mở notebook, đăng nhập đúng tài khoản Google.\n"
            "2. Chọn model/CPU hoặc CUDA rồi chạy cell.\n"
            "3. Nhập mã notebook hiện ra, kiểm tra thông tin và xác nhận.\n\n"
            "Chỉ duyệt mã từ notebook bạn vừa chạy. Dừng notebook cũ cùng worker trước khi ghép lại. "
            "Không cần sao chép token GitHub hay khóa broker."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.open_button = QPushButton("1. Mở notebook Colab")
        self.open_button.clicked.connect(self.open_notebook)
        layout.addWidget(self.open_button)
        self.code = QLineEdit()
        self.code.setPlaceholderText("Mã hiện trong notebook, ví dụ ABCD-EFGH")
        self.code.setMaxLength(12)
        self.code.textChanged.connect(self._invalidate)
        layout.addWidget(self.code)
        self.inspect_button = QPushButton("2. Kiểm tra mã")
        self.inspect_button.clicked.connect(self.inspect_code)
        layout.addWidget(self.inspect_button)
        self.status = QLabel("Chưa nhập mã. Mã có hiệu lực 10 phút.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.approve_button = QPushButton("3. Xác nhận ghép nối")
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(self.approve)
        layout.addWidget(self.approve_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def open_notebook(self):
        try:
            url = notebook_url(self.profile.worker_id)
        except ValueError as error:
            self.status.setText(str(error))
            return
        if not QDesktopServices.openUrl(QUrl(url)):
            self.status.setText("Không mở được trình duyệt. Mở notebook trong thư mục colab của dự án.")

    def _invalidate(self):
        self.preview = None
        self.approve_button.setEnabled(False)
        if not self._busy:
            self.status.setText("Bấm Kiểm tra mã để đối chiếu với worker đang chọn.")

    def _busy_state(self, busy: bool):
        self._busy = busy
        self.code.setEnabled(not busy)
        self.inspect_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.buttons.setEnabled(not busy)
        self.approve_button.setEnabled(not busy and self.preview is not None)

    def _start(self, function, complete):
        self._busy_state(True)
        task = FunctionTask(function)
        self._task = task
        task.signals.completed.connect(complete)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def inspect_code(self):
        code = self.code.text().strip().upper()
        compact = code.replace("-", "").replace(" ", "")
        if len(compact) != 8 or not compact.isascii() or not compact.isalnum():
            self.status.setText("Nhập đúng mã 8 ký tự notebook vừa hiện, ví dụ ABCD-EFGH.")
            return
        self.preview = None
        self.status.setText("Đang kiểm tra mã với broker...")
        self._start(lambda: self.client.inspect_pairing(code), self._inspected)

    def _inspected(self, preview: PairingPreview):
        self._task = None
        if preview.worker_id != self.profile.worker_id or preview.provider != self.provider:
            self.preview = None
            self._busy_state(False)
            self.status.setText(
                f"Không khớp: notebook là {preview.worker_id} / {preview.provider}, "
                f"Studio đang chọn {self.profile.worker_id} / {self.provider}. "
                "Chọn lại worker/model đúng trong Studio hoặc notebook; chưa cấp quyền."
            )
            return
        self.preview = preview
        self._busy_state(False)
        name = "VieNeu v3 · preset + clone" if preview.provider == "vieneu_v3" else "ZeroTTS"
        self.status.setText(
            f"Đúng worker: {preview.worker_id}\nModel: {name} · {preview.device.upper()}\n"
            f"Chỉ quyền worker trong {preview.session_hours} giờ. Hãy xác nhận nếu đúng notebook của bạn."
        )

    def approve(self):
        if self.preview is None or self._busy:
            return
        preview, code = self.preview, self.code.text().strip().upper()
        # Separate deliberate user click after inspection is the authorization boundary.
        self.preview = None
        self.status.setText("Đang xác nhận ghép nối. Không gửi lại nếu kết nối bị gián đoạn...")
        self._start(lambda: self.client.approve_pairing(code, preview), self._approved)

    def _approved(self, result):
        self._task = None
        self.preview = None
        self._busy_state(False)
        self.code.clear()
        self.status.setText(
            "Đã cấp quyền. Colab đang tải source/môi trường/model — chưa chắc đã sẵn sàng.\n"
            "Giữ cell notebook chạy. Khi thấy WORKER READY, đóng cửa sổ này và bấm Kiểm tra kết nối."
        )

    def _failed(self, error: str):
        self._task = None
        self.preview = None
        self._busy_state(False)
        self.status.setText(
            f"Không hoàn tất: {error}\nNếu vừa xác nhận, kiểm tra notebook trước; "
            "không tự gửi lại xác nhận. Có thể chạy lại notebook để lấy mã mới."
        )

    def reject(self):
        if not self._busy:
            super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
        else:
            super().closeEvent(event)
