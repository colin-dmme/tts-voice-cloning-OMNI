"""Shared application context handed to every page.

Bundles the core facade, hardware probe, safety gate, preferences, and a few
GUI callbacks so pages never reach back into MainWindow internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from omni_tts_core.app_controller import AppController
from omni_tts_core.hardware_monitor import HardwareProbe
from omni_tts_core.safety_coordinator import SafetyGate
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.preferences import QtPreferences

SettingsProvider = Callable[[], GenerationSettings]


@dataclass
class AppContext:
    controller: AppController
    probe: HardwareProbe
    safety_gate: SafetyGate
    preferences: QtPreferences
    log: Callable[[str], None]
    set_worker_status: Callable[[str, str], None]
    show_page: Callable[[str], None]
    # A page (the studio) registers a getter for the live generation settings so
    # the hardware chip/chart can reflect the active GPU-safety thresholds.
    register_settings_provider: Callable[[SettingsProvider], None]
