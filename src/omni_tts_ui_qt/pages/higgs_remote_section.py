"""Qt widgets for Higgs Remote; protocol behavior remains in ``core.remote``."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from omni_tts_core.ui_presenters.tooltips import tooltip
from omni_tts_core.remote.higgs_controls import (
    HIGGS_EMOTION_CHOICES,
    HIGGS_EXPRESSIVENESS_CHOICES,
    HIGGS_OPTIONAL_SAMPLING_DISPLAY,
    HIGGS_PITCH_CHOICES,
    HIGGS_RESPONSE_FORMAT_CHOICES,
    HIGGS_SPEED_CHOICES,
    HIGGS_STYLE_CHOICES,
)
from omni_tts_shared.schemas import HiggsTtsOptions, RemoteEndpointOptions
from omni_tts_ui_qt.widgets.common import dspin_for, make_combo, spin_for

class HiggsRemoteGroup(QWidget):
    check_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.endpoint_url = self._line(
            "URL endpoint:",
            "https://…/v1/audio/speech",
            "higgs_endpoint",
        )
        check_row = QWidget()
        check_layout = QHBoxLayout(check_row)
        check_layout.setContentsMargins(0, 0, 0, 0)
        self.check_button = QPushButton("Kiểm tra kết nối")
        self.check_button.setToolTip(tooltip("higgs_check"))
        self.check_status = QLabel("Chưa kiểm tra URL hiện tại.")
        self.check_status.setWordWrap(True)
        self.check_status.setObjectName("hint")
        check_layout.addWidget(self.check_button)
        check_layout.addWidget(self.check_status, 1)
        self.form.addRow(check_row)
        self.check_button.clicked.connect(self.check_requested)

        auth_note = QLabel(
            "Phiên bản này: không authorization. Kiến trúc đã chừa chế độ Bearer "
            "qua biến môi trường cho gateway/GPU thuê sau này."
        )
        auth_note.setWordWrap(True)
        auth_note.setObjectName("hint")
        auth_note.setToolTip(tooltip("higgs_auth"))
        self.form.addRow(auth_note)

        self.model = self._line("Model API:", "Để trống = model server đang serve", "higgs_model")
        self.voice = self._line("Voice API (nâng cao):", "default", "higgs_voice")
        self.stream = QCheckBox("Streaming PCM (khuyến nghị qua Cloudflare)")
        self.stream.setChecked(True)
        self.stream.setToolTip(tooltip("higgs_stream"))
        self.form.addRow(self.stream)
        self.response_format = make_combo(list(HIGGS_RESPONSE_FORMAT_CHOICES), "pcm")
        self.response_format.setToolTip(tooltip("higgs_format"))
        self.form.addRow("Response format:", self.response_format)

        self.temperature = dspin_for(
            "temperature", 1.0, "higgs_temperature", schema=HiggsTtsOptions
        )
        self.max_new_tokens = spin_for(
            "max_new_tokens", 2048, "higgs_max_tokens", schema=HiggsTtsOptions
        )
        self.top_p_enabled, self.top_p = self._optional_number(
            "Gửi Top-P",
            dspin_for(
                "top_p",
                HIGGS_OPTIONAL_SAMPLING_DISPLAY["top_p"],
                "higgs_top_p",
                schema=HiggsTtsOptions,
            ),
        )
        self.top_k_enabled, self.top_k = self._optional_number(
            "Gửi Top-K",
            spin_for(
                "top_k",
                HIGGS_OPTIONAL_SAMPLING_DISPLAY["top_k"],
                "higgs_top_k",
                schema=HiggsTtsOptions,
            ),
        )
        self.seed = spin_for("seed", -1, "higgs_seed", schema=HiggsTtsOptions)
        self.codec_frames = spin_for(
            "initial_codec_chunk_frames",
            1,
            "higgs_codec_frames",
            schema=HiggsTtsOptions,
        )
        self.concurrency = spin_for(
            "concurrency", 1, "higgs_concurrency", schema=HiggsTtsOptions
        )
        self.form.addRow("Temperature:", self.temperature)
        self.form.addRow("Max new tokens:", self.max_new_tokens)
        self.form.addRow("Seed (-1 = ngẫu nhiên):", self.seed)
        self.form.addRow("Codec frames đầu:", self.codec_frames)
        self.form.addRow("Request đồng thời:", self.concurrency)

        self.connect_timeout = dspin_for(
            "connect_timeout_seconds",
            10.0,
            "higgs_connect_timeout",
            schema=RemoteEndpointOptions,
        )
        self.request_timeout = dspin_for(
            "request_timeout_seconds",
            600.0,
            "higgs_request_timeout",
            schema=RemoteEndpointOptions,
        )
        self.retries = spin_for(
            "max_retries", 1, "higgs_retries", schema=RemoteEndpointOptions
        )
        self.form.addRow("Connect timeout (giây):", self.connect_timeout)
        self.form.addRow("Request timeout (giây):", self.request_timeout)
        self.form.addRow("Retry lỗi tạm thời:", self.retries)

        self.emotion = make_combo(list(HIGGS_EMOTION_CHOICES), "")
        self.style = make_combo(list(HIGGS_STYLE_CHOICES), "")
        self.speed = make_combo(list(HIGGS_SPEED_CHOICES), "")
        self.pitch = make_combo(list(HIGGS_PITCH_CHOICES), "")
        self.expressiveness = make_combo(list(HIGGS_EXPRESSIVENESS_CHOICES), "")
        for widget, key in (
            (self.emotion, "higgs_emotion"),
            (self.style, "higgs_style"),
            (self.speed, "higgs_speed"),
            (self.pitch, "higgs_pitch"),
            (self.expressiveness, "higgs_expressiveness"),
        ):
            widget.setToolTip(tooltip(key))
        self.form.addRow("Emotion:", self.emotion)
        self.form.addRow("Style:", self.style)
        self.form.addRow("Speed/prosody:", self.speed)
        self.form.addRow("Pitch/prosody:", self.pitch)
        self.form.addRow("Expressiveness:", self.expressiveness)

        self.delivery_tags = self._line(
            "Tags nâng cao:",
            "Pause/SFX/custom token chèn trước toàn đoạn",
            "higgs_tags",
        )
        self.stream.toggled.connect(self._sync_stream_format)
        self._sync_stream_format(True)

    def _line(self, label: str, placeholder: str, tooltip_key: str) -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.setToolTip(tooltip(tooltip_key))
        self.form.addRow(label, widget)
        return widget

    def _optional_number(self, label: str, number):
        enabled = QCheckBox(label)
        number.setEnabled(False)
        enabled.toggled.connect(number.setEnabled)
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(enabled)
        layout.addWidget(number, 1)
        self.form.addRow(holder)
        return enabled, number

    def _sync_stream_format(self, streaming: bool) -> None:
        if streaming:
            index = self.response_format.findData("pcm")
            self.response_format.setCurrentIndex(index)
        self.response_format.setEnabled(not streaming)

    def widgets(self) -> list[QWidget]:
        return [
            self.endpoint_url,
            self.model,
            self.voice,
            self.stream,
            self.response_format,
            self.temperature,
            self.max_new_tokens,
            self.top_p_enabled,
            self.top_p,
            self.top_k_enabled,
            self.top_k,
            self.seed,
            self.codec_frames,
            self.concurrency,
            self.connect_timeout,
            self.request_timeout,
            self.retries,
            self.emotion,
            self.style,
            self.speed,
            self.pitch,
            self.expressiveness,
            self.delivery_tags,
        ]

    def set_checking(self, checking: bool, message: str) -> None:
        self.check_button.setEnabled(not checking)
        self.check_status.setText(message)
