"""Background execution, progress, cancellation and retry for MCP jobs."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from threading import Event, Lock
from typing import Any

from omni_tts_core.app_controller import AppController
from omni_tts_core.gpu_safety_preferences import GpuSafetyPreferences
from omni_tts_core.progress import ProgressEvent
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import GenerationCancelled

from .contracts import FileGenerationInput, TextGenerationInput
from .job_store import McpJobStore, TERMINAL_STATUSES, now_utc


class McpJobManager:
    def __init__(
        self,
        controller: AppController,
        store: McpJobStore,
        max_workers: int = 4,
        gpu_preferences: GpuSafetyPreferences | None = None,
    ) -> None:
        self.controller = controller
        self.store = store
        self.gpu_preferences = gpu_preferences or GpuSafetyPreferences()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="colin-mcp"
        )
        self._lock = Lock()
        self._cancel_events: dict[str, Event] = {}
        self._futures: dict[str, Future] = {}

    def start_text(self, request: TextGenerationInput) -> dict[str, Any]:
        self._settings_for(request)
        return self._submit("text", request.model_dump(mode="json"))

    def start_files(self, request: FileGenerationInput) -> dict[str, Any]:
        self._settings_for(request)
        return self._submit("files", request.model_dump(mode="json"))

    def _submit(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.store.create(kind, payload)
        job_id = record["job_id"]
        cancel_event = Event()
        with self._lock:
            self._cancel_events[job_id] = cancel_event
            future = self._executor.submit(
                self._run, job_id, kind, payload, cancel_event
            )
            self._futures[job_id] = future
        future.add_done_callback(lambda _future: self._forget(job_id))
        return public_job(record)

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(job_id, None)
            self._futures.pop(job_id, None)

    def _progress(self, job_id: str, event: ProgressEvent) -> None:
        self.store.update(
            job_id, progress=round(event.percent, 2), message=event.message
        )

    def _settings_for(
        self, request: TextGenerationInput | FileGenerationInput
    ) -> GenerationSettings:
        return request.to_settings(self.gpu_preferences.load())

    def _run(
        self,
        job_id: str,
        kind: str,
        payload: dict[str, Any],
        cancel_event: Event,
    ) -> None:
        self.store.update(
            job_id, status="running", message="Đang xử lý", started_at=now_utc()
        )
        try:
            if kind == "text":
                request = TextGenerationInput.model_validate(payload)
                result = self.controller.generate_text(
                    request.text,
                    self._settings_for(request),
                    progress_callback=lambda event: self._progress(job_id, event),
                    cancel_event=cancel_event,
                )
                result_data = result.model_dump(mode="json")
            else:
                request = FileGenerationInput.model_validate(payload)
                tasks = [
                    (f"mcp-{index}", Path(path))
                    for index, path in enumerate(request.source_files, 1)
                ]
                outcomes = self.controller.generate_files(
                    tasks,
                    self._settings_for(request),
                    progress_callback=lambda event: self._progress(job_id, event),
                    cancel_event=cancel_event,
                )
                result_data = {"files": [_jsonable(item) for item in outcomes]}
            self.store.update(
                job_id,
                status="succeeded",
                progress=100.0,
                message="Hoàn tất",
                result_json=json.dumps(result_data, ensure_ascii=False),
                finished_at=now_utc(),
            )
        except GenerationCancelled as exc:
            self.store.update(
                job_id,
                status="cancelled",
                message=str(exc),
                error=str(exc),
                finished_at=now_utc(),
            )
        except Exception as exc:
            self.store.update(
                job_id,
                status="failed",
                message="Tạo giọng thất bại",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=now_utc(),
            )

    def get(self, job_id: str) -> dict[str, Any]:
        return public_job(self.store.get(job_id))

    def list(self, limit: int = 20, status: str | None = None) -> dict[str, Any]:
        items = [public_job(item) for item in self.store.list(limit, status)]
        return {"count": len(items), "jobs": items}

    def cancel(self, job_id: str) -> dict[str, Any]:
        record = self.store.get(job_id)
        if record["status"] in TERMINAL_STATUSES:
            return public_job(record)
        with self._lock:
            cancel_event = self._cancel_events.get(job_id)
            future = self._futures.get(job_id)
            if cancel_event is not None:
                cancel_event.set()
            cancelled_before_start = future.cancel() if future is not None else False
        if cancelled_before_start:
            record = self.store.update(
                job_id,
                status="cancelled",
                message="Đã hủy trước khi bắt đầu",
                finished_at=now_utc(),
            )
        else:
            record = self.store.update(
                job_id, status="cancelling", message="Đang hủy an toàn..."
            )
        return public_job(record)

    def retry(self, job_id: str) -> dict[str, Any]:
        record = self.store.get(job_id)
        if record["status"] not in TERMINAL_STATUSES:
            raise ValueError("Chỉ có thể thử lại job đã kết thúc")
        if record["kind"] == "text":
            return self.start_text(TextGenerationInput.model_validate(record["request"]))
        return self.start_files(FileGenerationInput.model_validate(record["request"]))

    def active_count(self) -> int:
        with self._lock:
            return len(self._futures)


def public_job(record: dict[str, Any]) -> dict[str, Any]:
    payload = record["request"]
    summary: dict[str, Any] = {
        "model_id": payload.get("model_id"),
        "voice": payload.get("voice"),
        "output": payload.get("output"),
    }
    if record["kind"] == "text":
        content = str(payload.get("text") or "")
        summary.update(text_length=len(content), text_preview=content[:120])
    else:
        summary["source_files"] = payload.get("source_files", [])
    return {
        "job_id": record["job_id"],
        "kind": record["kind"],
        "status": record["status"],
        "progress": record["progress"],
        "message": record["message"],
        "error": record["error"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "started_at": record["started_at"],
        "finished_at": record["finished_at"],
        "request_summary": summary,
        "result": record["result"],
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value