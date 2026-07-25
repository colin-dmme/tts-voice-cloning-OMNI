"""Dark theme (QSS + palette) for Colin TTS Studio.

Palette follows the S3Voice reference: near-black surfaces, violet accent
(#8b5cf6), amber warning (#f59e0b). Applied globally in main().
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Shared palette constants (also used by hand-painted widgets).
BG = "#0b0b14"
SURFACE = "#11111b"
SURFACE_ALT = "#0d0d17"
BORDER = "#25253a"
GRID = "#2b2b3d"
ACCENT = "#8b5cf6"
ACCENT_STRONG = "#7c3aed"
WARNING = "#f59e0b"
TEXT = "#e4e4ef"
MUTED = "#a1a1b3"
OK = "#34d399"
DANGER = "#f87171"

DARK_STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QFrame#hardwareBar {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#pageTitle {{ font-size: 18px; font-weight: 700; color: #e9e6ff; }}
QLabel#sidebarTitle {{ font-size: 12px; font-weight: 700; color: {MUTED}; }}
QLabel#hint {{ color: {MUTED}; }}
QLabel#safetyChip {{
    border-radius: 9px; padding: 3px 10px; font-weight: 600;
    background: #14241a; color: {OK};
}}
QFrame#collapsibleSection {{
    background: {SURFACE_ALT};
    border: 1px solid #29293d;
    border-radius: 8px;
}}
QFrame#sectionHeader {{ background: #12121f; border: none; border-radius: 7px; }}
QPushButton#sectionToggle {{
    background: transparent; border: none; color: #c4b5fd;
    font-weight: 700; text-align: left; padding: 2px 4px;
}}
QPushButton#sectionToggle:hover {{ background: transparent; border: none; color: #ddd6fe; }}
QPushButton#sectionToggle:pressed, QPushButton#sectionToggle:checked {{
    background: transparent; border: none;
}}
/* Checkboxes / radios: Fusion's default indicators are nearly invisible on this
   dark palette, so draw them explicitly with a strong border and filled state.
   Declared BEFORE the [active] rules so the ACTIVE chip keeps its own colour. */
QCheckBox, QRadioButton {{ spacing: 8px; padding: 2px 0; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px; height: 17px;
    border: 2px solid #6b6b8a;
    background: #16162a;
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: #c4b5fd;
}}
QRadioButton::indicator:checked {{
    border-color: #c4b5fd;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 #ffffff, stop:0.42 #c4b5fd, stop:0.5 {ACCENT}, stop:1 {ACCENT});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: #3a3a52; background: #14141f;
}}
QCheckBox:checked, QRadioButton:checked {{ color: #ffffff; font-weight: 600; }}
QCheckBox[active="true"] {{ color: {OK}; font-weight: 700; }}
QCheckBox[active="false"] {{ color: {MUTED}; font-weight: 700; }}
QToolBar#railBar {{ background: {SURFACE}; border: none; border-right: 1px solid {BORDER}; }}
QToolBar#railBar QToolButton {{
    background: transparent; border: none; border-radius: 8px;
    padding: 10px 6px; color: {MUTED}; font-size: 11px;
}}
QToolBar#railBar QToolButton:hover {{ background: #1c1c2c; color: {TEXT}; }}
QToolBar#railBar QToolButton:checked {{ background: #251a45; color: #c4b5fd; }}
QPushButton {{
    background: #1a1a2a; border: 1px solid #34344b;
    border-radius: 7px; padding: 8px 12px;
}}
QPushButton:hover {{ background: #24243a; border-color: {ACCENT_STRONG}; }}
QPushButton:pressed {{ background: #312e81; }}
QPushButton:disabled {{ color: #686878; background: #12121d; }}
QPushButton#primaryButton {{
    background: #6d28d9; border-color: {ACCENT}; font-weight: 600; color: white;
}}
QPushButton#primaryButton:hover {{ background: {ACCENT_STRONG}; }}
QPushButton#dangerButton:hover {{ border-color: {DANGER}; }}
QToolButton {{
    background: #1a1a2a; border: 1px solid #34344b;
    border-radius: 7px; padding: 7px 10px;
}}
QToolButton:hover, QToolButton:checked {{ background: #24243a; border-color: {ACCENT_STRONG}; }}
QToolButton::menu-indicator {{ image: none; }}
QMenu {{ background: #141421; border: 1px solid #34344b; padding: 5px; }}
QMenu::item {{ border-radius: 5px; padding: 7px 24px 7px 10px; }}
QMenu::item:selected {{ background: #312e81; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox,
QListWidget, QTableView, QListView {{
    background: {SURFACE}; border: 1px solid #2a2a3d; border-radius: 6px;
    selection-background-color: #5b21b6; padding: 5px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #141421; border: 1px solid #34344b; selection-background-color: #312e81;
}}
QTableView {{ gridline-color: #202033; alternate-background-color: {SURFACE_ALT}; }}
QHeaderView::section {{
    background: #151522; color: #b7b7c9; border: none;
    border-right: 1px solid #28283a; border-bottom: 1px solid #28283a;
    padding: 8px; font-weight: 600;
}}
QListWidget::item {{ border-radius: 7px; padding: 9px; margin: 2px; }}
QListWidget::item:selected {{ background: #291751; color: #c4b5fd; }}
QTabBar::tab {{
    background: #14141f; color: {MUTED}; padding: 8px 16px;
    border-top-left-radius: 7px; border-top-right-radius: 7px; margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QProgressBar {{
    background: {SURFACE}; border: 1px solid #2a2a3d; border-radius: 6px;
    text-align: center; height: 18px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollBar:vertical {{ background: #0d0d16; width: 11px; }}
QScrollBar::handle:vertical {{ background: #34344b; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: #0d0d16; height: 11px; }}
QScrollBar::handle:horizontal {{ background: #34344b; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QDockWidget {{ color: {MUTED}; titlebar-close-icon: none; }}
QDockWidget::title {{ background: #10101b; padding: 6px 10px; }}
QStatusBar {{ background: #10101b; color: {MUTED}; }}
QToolTip {{ background: #1c1c2b; color: #ffffff; border: 1px solid #4c1d95; }}
QSplitter::handle {{ background: {BORDER}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_STRONG))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1c1c2b"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)
