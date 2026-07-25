"""MainWindow: the single-window studio shell.

Left icon rail (LA-Studio style) switches pages in a QStackedWidget. The header
carries the page title, the live HardwareBar, a SafetyChip, and a toggle for the
temperature sparkline. A bottom dock shows the system log. Telemetry is global —
one TelemetryThread feeds the bar/chart/chip for every page and provider.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from omni_tts_core.hardware_monitor import HardwareSnapshot
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.background import TelemetryThread
from omni_tts_ui_qt.context import AppContext, SettingsProvider
from omni_tts_ui_qt.preferences import QtPreferences
from omni_tts_ui_qt.widgets.hardware import HardwareBar, SafetyChip, TemperatureChart

# (key, title, rail label) — a factory(context) -> QWidget is supplied per page.
PageFactory = Callable[[AppContext], QWidget]


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller,
        probe,
        safety_gate,
        preferences: QtPreferences,
        page_factories: list[tuple[str, str, str, PageFactory]],
    ) -> None:
        super().__init__()
        self.setWindowTitle("Colin TTS Studio")
        self.setMinimumSize(1180, 760)
        self._prefs = preferences
        self._prefs_data = preferences.load()
        self._settings_provider: SettingsProvider | None = None
        self._page_keys: list[str] = []

        self.context = AppContext(
            controller=controller,
            probe=probe,
            safety_gate=safety_gate,
            preferences=preferences,
            log=self.log,
            set_worker_status=self._set_worker_status,
            show_page=self.show_page,
            register_settings_provider=self.register_settings_provider,
        )

        self._build_rail(page_factories)
        self._build_central(page_factories)
        self._build_log_dock()
        self._start_telemetry()
        self._restore_layout()

    # --- Layout construction -----------------------------------------------

    def _build_rail(self, page_factories) -> None:
        rail = QToolBar("Điều hướng")
        rail.setObjectName("railBar")
        rail.setMovable(False)
        rail.setOrientation(Qt.Orientation.Vertical)
        rail.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail)
        self._rail_group = QActionGroup(self)
        self._rail_group.setExclusive(True)
        for index, (key, title, icon, _factory) in enumerate(page_factories):
            action = QAction(f"{icon}\n{title}", self)
            action.setCheckable(True)
            action.setData(index)
            action.triggered.connect(lambda _checked, i=index: self._select_page(i))
            self._rail_group.addAction(action)
            rail.addAction(action)

    def _build_central(self, page_factories) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self.page_title = QLabel("")
        self.page_title.setObjectName("pageTitle")
        self.safety_chip = SafetyChip()
        self.hardware_bar = HardwareBar()
        self.chart_toggle = QPushButton("Biểu đồ nhiệt")
        self.chart_toggle.setCheckable(True)
        self.chart_toggle.setChecked(bool(self._prefs_data.get("chart_visible", True)))
        self.chart_toggle.toggled.connect(self._toggle_chart)
        header.addWidget(self.page_title)
        header.addStretch()
        header.addWidget(self.safety_chip)
        header.addWidget(self.hardware_bar, 1)
        header.addWidget(self.chart_toggle)
        outer.addLayout(header)

        self.temperature_chart = TemperatureChart()
        outer.addWidget(self.temperature_chart)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        for key, title, _icon, factory in page_factories:
            self._page_keys.append(key)
            widget = factory(self.context)
            widget.setProperty("pageTitle", title)
            self.stack.addWidget(widget)

        self.setCentralWidget(central)
        self.temperature_chart.setVisible(self.chart_toggle.isChecked())

    def _build_log_dock(self) -> None:
        dock = QDockWidget("Nhật ký hệ thống", self)
        dock.setObjectName("logDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self._log_dock = dock

    def _start_telemetry(self) -> None:
        self.telemetry = TelemetryThread(self.context.probe, interval_ms=2000)
        self.telemetry.snapshot_ready.connect(self._on_snapshot)
        self.telemetry.start()

    # --- Page navigation ----------------------------------------------------

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        widget = self.stack.currentWidget()
        self.page_title.setText(str(widget.property("pageTitle") or ""))
        self._prefs_data["active_page"] = index

    def show_page(self, key: str) -> None:
        if key in self._page_keys:
            index = self._page_keys.index(key)
            actions = self._rail_group.actions()
            if index < len(actions):
                actions[index].setChecked(True)
            self._select_page(index)

    # --- Telemetry / status -------------------------------------------------

    def register_settings_provider(self, provider: SettingsProvider) -> None:
        self._settings_provider = provider

    def _current_settings(self) -> GenerationSettings:
        if self._settings_provider is not None:
            try:
                return self._settings_provider()
            except Exception:
                pass
        return GenerationSettings()

    def _on_snapshot(self, snapshot: HardwareSnapshot) -> None:
        self.hardware_bar.update_snapshot(snapshot)
        self.temperature_chart.add_snapshot(snapshot)
        settings = self._current_settings()
        assessment = self.context.safety_gate.assess(snapshot, settings)
        self.safety_chip.update_assessment(assessment)
        self.temperature_chart.set_warning_temperature(assessment.abort_temperature_c)

    def _set_worker_status(self, status: str, message: str) -> None:
        self.hardware_bar.update_worker(status, message)

    def _toggle_chart(self, visible: bool) -> None:
        self.temperature_chart.setVisible(visible)
        self._prefs_data["chart_visible"] = visible

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

    # --- Persistence / lifecycle -------------------------------------------

    def _restore_layout(self) -> None:
        geometry = self._prefs_data.get("window_geometry_b64") or ""
        state = self._prefs_data.get("window_state_b64") or ""
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode("ascii")))
        index = int(self._prefs_data.get("active_page", 0) or 0)
        actions = self._rail_group.actions()
        if actions:
            index = min(index, len(actions) - 1)
            actions[index].setChecked(True)
            self._select_page(index)

    def collect_settings(self) -> None:
        """Ask each page to persist its state into the shared prefs dict."""
        for index in range(self.stack.count()):
            widget = self.stack.widget(index)
            saver = getattr(widget, "save_preferences", None)
            if callable(saver):
                try:
                    saver(self._prefs_data)
                except Exception:
                    pass

    def _busy_pages(self) -> bool:
        for index in range(self.stack.count()):
            widget = self.stack.widget(index)
            checker = getattr(widget, "is_busy", None)
            if callable(checker) and checker():
                return True
        return False

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy_pages():
            answer = QMessageBox.question(
                self,
                "Đang chạy tác vụ",
                "Có tác vụ đang chạy. Thoát và hủy tác vụ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.telemetry.requestInterruption()
        self.telemetry.wait(1500)
        self.collect_settings()
        self._prefs_data["window_geometry_b64"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self._prefs_data["window_state_b64"] = bytes(self.saveState().toBase64()).decode("ascii")
        self._prefs.save(self._prefs_data)
        super().closeEvent(event)
