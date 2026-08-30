"""Qt table model + progress delegate over the core FileQueueStore items."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionProgressBar

from omni_tts_core.file_queue import (
    STATUS_LABELS,
    FileQueueItem,
    FileQueuePronunciationMode,
    FileQueueStatus,
)
from omni_tts_core.ui_presenters.labels import format_duration

_COLUMNS = [
    "Tên file",
    "Ký tự",
    "Số đoạn",
    "Cách đọc",
    "Trạng thái",
    "Tiến độ",
    "Thời lượng",
    "Lần chạy",
    "Kết quả / Lỗi",
]

_STATUS_COLORS = {
    FileQueueStatus.PENDING: "#a1a1b3",
    FileQueueStatus.RUNNING: "#8b5cf6",
    FileQueueStatus.DONE: "#34d399",
    FileQueueStatus.FAILED: "#f87171",
    FileQueueStatus.CANCELLED: "#fbbf24",
    FileQueueStatus.INTERRUPTED: "#fbbf24",
    FileQueueStatus.OUTDATED: "#60a5fa",
}


class QueueTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[FileQueueItem] = []
        self._preset_names: dict[str, str] = {}

    def set_items(
        self,
        items: list[FileQueueItem],
        preset_names: dict[str, str] | None = None,
    ) -> None:
        self.beginResetModel()
        self._items = items
        self._preset_names = dict(preset_names or {})
        self.endResetModel()

    def item_at(self, row: int) -> FileQueueItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return item.source_path.name
            if column == 1:
                return f"{item.char_count:,}"
            if column == 2:
                return f"{item.unit_count:,}" if item.unit_count >= 0 else "—"
            if column == 3:
                return self._pronunciation_text(item)
            if column == 4:
                return STATUS_LABELS.get(item.status, item.status.value)
            if column == 5:
                return int(item.progress_percent)
            if column == 6:
                return format_duration(item.duration_seconds)
            if column == 7:
                return str(item.attempt_count)
            if column == 8:
                return item.last_error or item.status_detail
        elif role == Qt.ItemDataRole.ForegroundRole and column == 4:
            return QColor(_STATUS_COLORS.get(item.status, "#e4e4ef"))
        elif role == Qt.ItemDataRole.ToolTipRole:
            if column == 2:
                return (
                    "Số file audio dự kiến khi bật “Tách mỗi đoạn/dòng SRT "
                    "thành file riêng”."
                )
            if column == 3:
                detail = item.pronunciation_details or "Chưa có chi tiết từ được áp dụng."
                return f"{self._pronunciation_text(item)}\n{detail}"
            return str(item.source_path)
        return None

    def _pronunciation_text(self, item: FileQueueItem) -> str:
        if item.pronunciation_mode == FileQueuePronunciationMode.OFF:
            binding = "Tắt"
        elif item.pronunciation_mode == FileQueuePronunciationMode.PRESET:
            names = [
                self._preset_names.get(preset_id, preset_id)
                for preset_id in item.pronunciation_preset_ids
            ]
            binding = "Preset: " + ", ".join(names)
        else:
            binding = "Theo Studio"
        if item.pronunciation_match_count < 0:
            return f"{binding} · chưa quét"
        stats = (
            f"{item.pronunciation_term_count} từ / "
            f"{item.pronunciation_match_count} lần"
        )
        if item.pronunciation_conflict_count:
            stats += f" / {item.pronunciation_conflict_count} xung đột"
        return f"{binding} · {stats}"


class ProgressBarDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        value = index.data(Qt.ItemDataRole.DisplayRole)
        try:
            progress = int(value)
        except (TypeError, ValueError):
            super().paint(painter, option, index)
            return
        bar = QStyleOptionProgressBar()
        bar.rect = QRect(option.rect).adjusted(4, 6, -4, -6)
        bar.minimum = 0
        bar.maximum = 100
        bar.progress = progress
        bar.text = f"{progress}%"
        bar.textVisible = True
        QApplication.style().drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter)
