"""Lazy application runtime used by MCP tools."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from omni_tts_core.app_controller import AppController
from omni_tts_core.safety_coordinator import SafetyGate
from omni_tts_core.service import TtsService

from .job_manager import McpJobManager
from .job_store import McpJobStore


class McpRuntime:
    def __init__(self) -> None:
        self._lock = RLock()
        self._controller: AppController | None = None
        self._jobs: McpJobManager | None = None

    @property
    def controller(self) -> AppController:
        with self._lock:
            if self._controller is None:
                service = TtsService()
                self._controller = AppController(
                    service=service, safety_gate=SafetyGate(service)
                )
            return self._controller

    @property
    def jobs(self) -> McpJobManager:
        with self._lock:
            if self._jobs is None:
                controller = self.controller
                database = (
                    controller.service.settings.project_root
                    / "config"
                    / "mcp_jobs.sqlite3"
                )
                self._jobs = McpJobManager(controller, McpJobStore(database))
            return self._jobs

    @property
    def database_path(self) -> Path:
        return (
            self.controller.service.settings.project_root
            / "config"
            / "mcp_jobs.sqlite3"
        )