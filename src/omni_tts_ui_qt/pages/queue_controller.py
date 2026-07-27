"""Non-widget glue between the file queue store, the GenerationWorker, and the UI.

Owns the FileQueueStore, translates FileGenerationEvents into store updates, and
exposes queue operations (add/delete/reset/clear/run/export). Kept widget-free so
its logic is unit-testable.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from omni_tts_core.app_controller import FileGenerationEvent
from omni_tts_core.file_queue import FileQueueItem, FileQueueStatus, FileQueueStore, settings_fingerprint
from omni_tts_core.path_intake import parse_path_text
from omni_tts_core.text.source_reader import SUPPORTED_TEXT_EXTENSIONS, count_source_text_chars
from omni_tts_core.ui_presenters import results
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_ui_qt.background import GenerationWorker
from omni_tts_ui_qt.context import AppContext


class QueueController(QObject):
    items_changed = Signal()
    log = Signal(str)
    worker_status = Signal(str, str)  # status, message
    progress = Signal(float, str)  # percent 0..1 (or -1 to hide), message
    run_state_changed = Signal(bool)  # True = a run is active

    def __init__(self, context: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.store = FileQueueStore()
        self._worker: GenerationWorker | None = None
        recovered = self.store.recover_and_validate()
        if recovered:
            self.log.emit(f"Đã khôi phục {recovered} mục hàng đợi sau lần đóng trước.")

    # --- Queue mutations ----------------------------------------------------

    def items(self) -> list[FileQueueItem]:
        return self.store.list_items()

    def add_paths(self, paths: list[Path]) -> None:
        sources: list[tuple[Path, int]] = []
        skipped = 0
        for path in paths:
            for resolved in _expand(path):
                try:
                    chars = count_source_text_chars(resolved)
                except Exception:
                    skipped += 1
                    continue
                sources.append((resolved, chars))
        if not sources:
            self.log.emit("Không tìm thấy file .txt/.md/.srt hợp lệ để thêm.")
            return
        added, duplicates = self.store.add_many(sources)
        parts = [f"Đã thêm {len(added)} file"]
        if duplicates:
            parts.append(f"{duplicates} trùng")
        if skipped:
            parts.append(f"{skipped} bỏ qua")
        self.log.emit(", ".join(parts) + ".")
        self.items_changed.emit()

    def add_from_text(self, text: str) -> None:
        self.add_paths(parse_path_text(text))

    def delete(self, item_ids: list[str]) -> None:
        removed = self.store.delete(item_ids)
        if removed:
            self.log.emit(f"Đã xóa {removed} mục khỏi hàng đợi.")
        self.items_changed.emit()

    def reset(self, item_ids: list[str]) -> None:
        self.store.reset(item_ids)
        self.items_changed.emit()

    def clear(self) -> None:
        removed = self.store.clear()
        self.log.emit(f"Đã xóa toàn bộ {removed} mục hàng đợi.")
        self.items_changed.emit()

    def mark_settings_outdated(self, settings: GenerationSettings) -> None:
        fingerprint = settings_fingerprint(settings.to_request("x").model_dump(mode="json"))
        changed = self.store.mark_settings_outdated(fingerprint)
        if changed:
            self.log.emit(f"{changed} file cần chạy lại do thiết lập thay đổi.")
            self.items_changed.emit()

    # --- Running the queue --------------------------------------------------

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, scope: str, settings: GenerationSettings, selected_ids: list[str]) -> None:
        if self.is_running():
            self.log.emit("Hàng đợi đang chạy.")
            return
        tasks = self._tasks_for(scope, selected_ids)
        if not tasks:
            self.log.emit("Không có file phù hợp để chạy.")
            return
        self._fingerprint = settings_fingerprint(settings.to_request("x").model_dump(mode="json"))
        self._worker = GenerationWorker(self.context.controller, "files", settings, tasks=tasks)
        self._worker.file_event.connect(self._on_file_event)
        self._worker.progress_event.connect(self._on_progress)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self.worker_status.emit("processing", f"Đang chạy {len(tasks)} file…")
        self.run_state_changed.emit(True)
        self._worker.start()

    def cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_cancel()
            self.log.emit("Đã yêu cầu hủy hàng đợi…")

    def _tasks_for(self, scope: str, selected_ids: list[str]) -> list[tuple[str, Path]]:
        selected = set(selected_ids)
        retry_states = {
            FileQueueStatus.FAILED, FileQueueStatus.CANCELLED,
            FileQueueStatus.INTERRUPTED, FileQueueStatus.OUTDATED,
        }
        tasks: list[tuple[str, Path]] = []
        for item in self.store.list_items():
            if item.status == FileQueueStatus.RUNNING:
                continue
            if scope == "selected" and item.item_id not in selected:
                continue
            if scope == "pending" and item.status != FileQueueStatus.PENDING:
                continue
            if scope == "failed" and item.status not in retry_states:
                continue
            tasks.append((item.item_id, item.source_path))
        return tasks

    # --- Worker event handlers ---------------------------------------------

    def _on_file_event(self, event: FileGenerationEvent) -> None:
        if event.status == FileQueueStatus.RUNNING:
            current = self.store.get(event.item_id)
            if current.status != FileQueueStatus.RUNNING:
                self.store.mark_running(event.item_id)
                current = self.store.get(event.item_id)
            # Status callbacks and concurrent requests may arrive late. Keep
            # the row monotonic and update only its message when the candidate
            # percentage is stale or equal.
            if event.progress_percent > current.progress_percent:
                self.store.update_progress(
                    event.item_id, event.progress_percent, event.message
                )
            else:
                self.store.update_detail(event.item_id, event.message)
        elif event.status == FileQueueStatus.DONE and event.result is not None:
            manifest = results.result_output_manifest(event.result)
            self.store.mark_done(
                event.item_id,
                job_id=event.result.job_id,
                output_paths=results.result_output_paths(event.result),
                fingerprint=getattr(self, "_fingerprint", ""),
                output_manifest=manifest,
                detail=event.message or "Đã tạo audio.",
            )
        elif event.status == FileQueueStatus.FAILED:
            self.store.mark_failed(event.item_id, event.error or event.message)
        elif event.status == FileQueueStatus.CANCELLED:
            self.store.mark_cancelled(event.item_id)
        self.items_changed.emit()

    def _on_progress(self, event) -> None:
        percent = (event.current / event.total) if event.total else 0.0
        self.progress.emit(percent, f"Toàn hàng đợi · {event.message}")
        self.log.emit(event.message)

    def _on_completed(self, _outcomes) -> None:
        self._finish("ready", "Hoàn tất hàng đợi.")

    def _on_failed(self, message: str) -> None:
        self.log.emit(f"Lỗi hàng đợi: {message}")
        self._finish("error", "Hàng đợi dừng do lỗi.")

    def _on_cancelled(self) -> None:
        self._finish("paused", "Đã hủy hàng đợi.")

    def _finish(self, status: str, message: str) -> None:
        self.worker_status.emit(status, message)
        self.log.emit(message)
        self.progress.emit(-1.0, "")
        self.run_state_changed.emit(False)
        self._worker = None
        self.items_changed.emit()

    # --- Export helpers -----------------------------------------------------

    def collect_paths(self, item_ids: list[str], kind: str) -> list[Path]:
        selected = set(item_ids)
        collected: list[Path] = []
        for item in self.store.list_items():
            if item.item_id not in selected or item.status != FileQueueStatus.DONE:
                continue
            collected.extend(item.output_manifest.paths_for(kind))
        return list(dict.fromkeys(collected))


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        found: list[Path] = []
        for ext in SUPPORTED_TEXT_EXTENSIONS:
            found.extend(sorted(path.rglob(f"*{ext}")))
        return found
    if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return [path]
    return []
