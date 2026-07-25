"""Live hardware widgets: status bar, temperature sparkline, safety chip.

Ported from the S3Voice reference (QPainter sparkline, deque history, dashed
warning line). Fed globally by the TelemetryThread — not tied to any single
model or provider.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from omni_tts_core.hardware_monitor import HardwareSnapshot
from omni_tts_core.safety_coordinator import SafetyAssessment
from omni_tts_ui_qt.theme import ACCENT, GRID, MUTED, SURFACE, WARNING

_WORKER_COLORS = {
    "ready": "#34d399",
    "processing": "#8b5cf6",
    "paused": "#fbbf24",
    "waiting": "#f59e0b",
    "error": "#f87171",
}

# Labels stay reason-neutral (a warning can be temperature *or* VRAM); the exact
# reasons go in the tooltip.
_CHIP_STYLES = {
    "ok": ("GPU an toàn", "#14241a", "#34d399"),
    "warning": ("Cảnh báo GPU", "#2a2410", "#fbbf24"),
    "hot": ("GPU quá nóng", "#2a1414", "#f87171"),
    "unavailable": ("Không có GPU", "#1c1c2b", "#a1a1b3"),
    "waiting": ("Đang chờ GPU an toàn…", "#2a2410", "#f59e0b"),
}


class HardwareBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("hardwareBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(16)
        self.status_label = QLabel("● Sẵn sàng")
        self.gpu_label = QLabel("GPU —")
        self.vram_label = QLabel("VRAM —")
        self.cpu_label = QLabel("CPU —")
        self.ram_label = QLabel("RAM —")
        layout.addWidget(self.status_label)
        layout.addStretch()
        for label in (self.gpu_label, self.vram_label, self.cpu_label, self.ram_label):
            layout.addWidget(label)

    def update_worker(self, status: str, message: str) -> None:
        color = _WORKER_COLORS.get(status, MUTED)
        self.status_label.setText(f'<span style="color:{color}">●</span> {message}')

    def update_snapshot(self, snapshot: HardwareSnapshot) -> None:
        if snapshot.gpu_temperature_c is None:
            self.gpu_label.setText("GPU —")
        else:
            util = snapshot.gpu_utilization_percent
            usage = f" · {util:.0f}%" if util is not None else ""
            self.gpu_label.setText(f"GPU {snapshot.gpu_temperature_c:.0f}°C{usage}")
        if snapshot.gpu_memory_used_mb is None or snapshot.gpu_memory_total_mb is None:
            self.vram_label.setText("VRAM —")
        else:
            self.vram_label.setText(
                f"VRAM {snapshot.gpu_memory_used_mb / 1024:.1f}/"
                f"{snapshot.gpu_memory_total_mb / 1024:.1f} GB"
            )
        cpu_parts = []
        if snapshot.cpu_utilization_percent is not None:
            cpu_parts.append(f"{snapshot.cpu_utilization_percent:.0f}%")
        if snapshot.cpu_temperature_c is not None:
            cpu_parts.append(f"{snapshot.cpu_temperature_c:.0f}°C")
        self.cpu_label.setText(f"CPU {' · '.join(cpu_parts)}" if cpu_parts else "CPU —")
        self.ram_label.setText(
            f"RAM {snapshot.ram_used_gb:.1f}/{snapshot.ram_total_gb:.1f} GB"
            if snapshot.ram_used_gb is not None
            else "RAM —"
        )


class TemperatureChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.values: deque[float | None] = deque(maxlen=120)
        self.warning_temperature = 80.0

    def add_snapshot(self, snapshot: HardwareSnapshot) -> None:
        self.values.append(snapshot.gpu_temperature_c)
        self.update()

    def set_warning_temperature(self, temperature: float) -> None:
        if temperature and temperature != self.warning_temperature:
            self.warning_temperature = float(temperature)
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -18)
        painter.fillRect(self.rect(), QColor(SURFACE))
        painter.setPen(QPen(QColor(GRID), 1))
        for index in range(1, 4):
            y = rect.top() + rect.height() * index / 4
            painter.drawLine(rect.left(), round(y), rect.right(), round(y))
        values = list(self.values)
        valid = [value for value in values if value is not None]
        if len(valid) < 2:
            painter.setPen(QColor("#71717a"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Chưa đủ dữ liệu nhiệt độ")
            return
        minimum = min(40.0, min(valid) - 5)
        maximum = max(100.0, max(valid) + 5)
        path = QPainterPath()
        started = False
        count = max(2, len(values))
        for index, value in enumerate(values):
            if value is None:
                started = False
                continue
            x = rect.left() + rect.width() * index / (count - 1)
            ratio = (value - minimum) / (maximum - minimum)
            y = rect.bottom() - rect.height() * ratio
            point = QPointF(x, y)
            if started:
                path.lineTo(point)
            else:
                path.moveTo(point)
                started = True
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.drawPath(path)
        warning_ratio = (self.warning_temperature - minimum) / (maximum - minimum)
        warning_y = rect.bottom() - rect.height() * warning_ratio
        painter.setPen(QPen(QColor(WARNING), 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), round(warning_y), rect.right(), round(warning_y))
        painter.setPen(QColor(MUTED))
        painter.drawText(
            10,
            self.height() - 4,
            f"GPU gần nhất: {valid[-1]:.0f}°C · cảnh báo {self.warning_temperature:.0f}°C",
        )


class SafetyChip(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("safetyChip")
        self._apply("unavailable")

    def update_assessment(self, assessment: SafetyAssessment) -> None:
        self._apply(assessment.level, assessment.reasons)

    def show_waiting(self) -> None:
        self._apply("waiting")

    def _apply(self, level: str, reasons: list[str] | None = None) -> None:
        label, background, color = _CHIP_STYLES.get(level, _CHIP_STYLES["unavailable"])
        self.setText(label)
        self.setStyleSheet(
            f"#safetyChip {{ background: {background}; color: {color};"
            " border-radius: 9px; padding: 3px 10px; font-weight: 600; }"
        )
        self.setToolTip("\n".join(reasons) if reasons else label)
