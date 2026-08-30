"""Application-wide protection against accidental parameter wheel changes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QScrollBar,
    QWidget,
)


class ParameterWheelGuard(QObject):
    """Keep wheel gestures for page scrolling, never parameter mutation.

    Installed once on QApplication, this also covers dialogs and controls built
    later from provider metadata. Typing, keyboard navigation, arrow buttons and
    explicit popup selection remain unchanged.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.Wheel:
            return False
        editor = self._parameter_editor(watched)
        if editor is None:
            return False
        scroll_area = self._nearest_scroll_area(editor)
        if scroll_area is not None:
            QCoreApplication.sendEvent(scroll_area.viewport(), event)
        return True

    @staticmethod
    def _parameter_editor(watched: QObject) -> QWidget | None:
        current = watched if isinstance(watched, QWidget) else None
        while current is not None:
            # A combo popup is an intentional browsing surface. Its list may
            # scroll, but the closed combo itself may not change by wheel.
            if isinstance(current, QAbstractItemView):
                return None
            if isinstance(current, QScrollBar):
                return None
            if isinstance(
                current,
                (QAbstractSpinBox, QAbstractSlider, QComboBox),
            ):
                return current
            current = current.parentWidget()
        return None

    @staticmethod
    def _nearest_scroll_area(widget: QWidget) -> QAbstractScrollArea | None:
        current = widget.parentWidget()
        while current is not None:
            if isinstance(current, QAbstractScrollArea):
                return current
            current = current.parentWidget()
        return None


def install_parameter_wheel_guard(app: QApplication) -> ParameterWheelGuard:
    """Install once and keep a stable reference for QApplication's lifetime."""
    existing = app.property("omniParameterWheelGuard")
    if isinstance(existing, ParameterWheelGuard):
        return existing
    guard = ParameterWheelGuard(app)
    app.installEventFilter(guard)
    app.setProperty("omniParameterWheelGuard", guard)
    return guard
