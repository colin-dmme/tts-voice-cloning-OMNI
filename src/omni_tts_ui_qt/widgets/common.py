"""Reusable Qt building blocks: collapsible sections, input factories, path bar."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.ui_presenters import field_limits, tooltips


class CollapsibleSection(QFrame):
    """A titled, collapsible container with an optional ACTIVE checkbox."""

    activation_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        expanded: bool = True,
        active: bool | None = None,
        active_text: str = "ACTIVE · ĐANG ÁP DỤNG",
        inactive_text: str = "DEACTIVE · KHÔNG ÁP DỤNG",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("sectionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        self._title = title
        # QPushButton (not QToolButton): only QPushButton honours QSS text-align,
        # which keeps the section title flush left.
        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("sectionToggle")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setFlat(True)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setText(f"{'▾' if expanded else '▸'}  {title}")
        self.toggle_button.setToolTip("Bấm để thu gọn hoặc mở rộng phần thiết lập này.")
        header_layout.addWidget(self.toggle_button, 1)

        self.activation: QCheckBox | None = None
        self._active_text = active_text
        self._inactive_text = inactive_text
        if active is not None:
            self.activation = QCheckBox()
            self.activation.setChecked(active)
            header_layout.addWidget(self.activation)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 10, 12, 12)
        outer.addWidget(header)
        outer.addWidget(self.body)
        self.body.setVisible(expanded)
        self.toggle_button.toggled.connect(self._set_expanded)
        if self.activation is not None:
            self.activation.toggled.connect(self._set_active)
            self._set_active(active)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle_button.setText(f"{'▾' if expanded else '▸'}  {self._title}")
        self.body.setVisible(expanded)

    def _set_active(self, active: bool) -> None:
        if self.activation is None:
            return
        self.activation.setText(self._active_text if active else self._inactive_text)
        self.activation.setProperty("active", active)
        self.activation.style().unpolish(self.activation)
        self.activation.style().polish(self.activation)
        self.body.setEnabled(active)
        self.activation_changed.emit(active)

    def set_title(self, title: str) -> None:
        self._title = title
        self._set_expanded(self.toggle_button.isChecked())

    def set_active(self, active: bool) -> None:
        if self.activation is not None:
            self.activation.setChecked(active)

    def is_active(self) -> bool:
        return self.activation is None or self.activation.isChecked()

    def set_visible(self, visible: bool) -> None:
        self.setVisible(visible)


def spin_for(field: str, value: int | None = None, tooltip_key: str = "") -> QSpinBox:
    """Integer input whose range comes from the request schema, never from here."""
    limit = field_limits.limit(field)
    minimum, maximum, step = limit.ints()
    default = value if value is not None else field_limits.default_of(field)
    widget = make_spin(minimum, maximum, int(limit.clamp(default or minimum)), step)
    if tooltip_key:
        widget.setToolTip(tooltips.tooltip(tooltip_key))
    return widget


def dspin_for(field: str, value: float | None = None, tooltip_key: str = "") -> QDoubleSpinBox:
    """Decimal input whose range comes from the request schema, never from here."""
    limit = field_limits.limit(field)
    default = value if value is not None else field_limits.default_of(field)
    widget = make_dspin(
        limit.widget_minimum,
        limit.maximum,
        limit.clamp(default if default is not None else limit.widget_minimum),
        limit.step,
        limit.decimals,
    )
    if tooltip_key:
        widget.setToolTip(tooltips.tooltip(tooltip_key))
    return widget


def make_spin(minimum: int, maximum: int, value: int, step: int = 1) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setSingleStep(step)
    widget.setValue(value)
    return widget


def make_dspin(
    minimum: float, maximum: float, value: float, step: float = 0.1, decimals: int = 2
) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setSingleStep(step)
    widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


def make_combo(choices: list[tuple[str, object]], value: object | None = None) -> QComboBox:
    widget = QComboBox()
    for label, data in choices:
        widget.addItem(label, data)
    if value is not None:
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
    return widget


def open_path(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        path = path.parent
    if not path.exists():
        return
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


class PathBar(QWidget):
    """Output-directory selector: line edit + browse + open-folder."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Cùng thư mục file nguồn (mặc định)")
        self.browse_button = QPushButton("Chọn…")
        self.open_button = QPushButton("Mở thư mục")
        layout.addWidget(QLabel("Nơi lưu:"))
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.browse_button)
        layout.addWidget(self.open_button)
        self.browse_button.clicked.connect(self._browse)
        self.open_button.clicked.connect(self._open)
        self.edit.textChanged.connect(self.changed)

    def value(self) -> Path | None:
        text = self.edit.text().strip()
        return Path(text) if text else None

    def set_value(self, path: Path | str | None) -> None:
        self.edit.setText(str(path) if path else "")

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất", self.edit.text())
        if selected:
            self.edit.setText(selected)

    def _open(self) -> None:
        value = self.value()
        if value:
            open_path(value)
