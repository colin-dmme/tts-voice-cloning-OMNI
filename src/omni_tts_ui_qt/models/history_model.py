"""Read-only Qt model for persistent generation history."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from omni_tts_core.generation_history import (
    HISTORY_STATUS_LABELS,
    GenerationHistoryEntry,
    HistoryStatus,
)
from omni_tts_core.ui_presenters.history_columns import (
    history_language_label,
    history_voice_label,
)
from omni_tts_core.ui_presenters.labels import format_duration

_COLUMNS = [
    "Thời gian",
    "Nguồn",
    "Loại",
    "Giọng",
    "Ngôn ngữ",
    "Ký tự",
    "Model",
    "Trạng thái",
    "Thời lượng",
]
_STATUS_COLUMN = 7

_STATUS_COLORS = {
    HistoryStatus.DONE: "#34d399",
    HistoryStatus.FAILED: "#f87171",
    HistoryStatus.CANCELLED: "#fbbf24",
}


class HistoryTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[GenerationHistoryEntry] = []
        self._profile_names: dict[str, str] = {}

    def set_items(self, items: list[GenerationHistoryEntry]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def set_profile_names(self, profile_names: dict[str, str]) -> None:
        """Refresh the profile id → name map used for the Giọng column."""
        self._profile_names = dict(profile_names or {})

    def item_at(self, row: int) -> GenerationHistoryEntry | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return _display_time(item.created_at)
            if column == 1:
                return item.source_label
            if column == 2:
                return "Văn bản" if item.mode == "text" else "File"
            if column == 3:
                return history_voice_label(item, self._profile_names)
            if column == 4:
                return history_language_label(item)
            if column == 5:
                return f"{item.char_count:,}"
            if column == 6:
                return item.model_id
            if column == _STATUS_COLUMN:
                return HISTORY_STATUS_LABELS.get(item.status, item.status.value)
            if column == 8:
                return format_duration(item.duration_seconds)
        if role == Qt.ItemDataRole.ForegroundRole and column == _STATUS_COLUMN:
            return QColor(_STATUS_COLORS.get(item.status, "#e4e4ef"))
        if role == Qt.ItemDataRole.ToolTipRole:
            details = [str(item.source_path or item.source_label)]
            details.append(
                "Có snapshot setting · Chuột phải để xem/khôi phục"
                if item.settings_snapshot
                else "Lịch sử cũ · Chưa có snapshot setting để khôi phục"
            )
            if item.error:
                details.append(item.error)
            return "\n".join(details)
        return None


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError):
        return value
