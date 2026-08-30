"""Non-widget glue between the file queue store, the GenerationWorker, and the UI.

Owns the FileQueueStore, translates FileGenerationEvents into store updates, and
exposes queue operations (add/delete/reset/clear/run/export). Kept widget-free so
its logic is unit-testable.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal

from omni_tts_core.app_controller import FileGenerationEvent, FileGenerationTask
from omni_tts_core.file_queue import (
    FileQueueItem,
    FileQueuePronunciationMode,
    FileQueueStatus,
    FileQueueStore,
    queue_settings_fingerprint,
)
from omni_tts_core.generation_history import (
    GenerationHistoryStore,
    HistoryStatus,
)
from omni_tts_core.path_intake import parse_path_text
from omni_tts_core.text.source_reader import (
    SUPPORTED_TEXT_EXTENSIONS,
    read_source_text,
    source_text_stats,
)
from omni_tts_core.ui_presenters import results
from omni_tts_core.ui_presenters.pronunciation import analysis_details
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.pronunciation import PronunciationReport, PronunciationSelection
from omni_tts_ui_qt.background import FunctionTask, GenerationWorker
from omni_tts_ui_qt.context import AppContext


class QueueController(QObject):
    items_changed = Signal()
    log = Signal(str)
    worker_status = Signal(str, str)  # status, message
    progress = Signal(float, str)  # percent 0..1 (or -1 to hide), message
    run_state_changed = Signal(bool)  # True = a run is active
    history_changed = Signal()

    def __init__(
        self,
        context: AppContext,
        history_store: GenerationHistoryStore | None = None,
        parent=None,
        store: FileQueueStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.store = store or FileQueueStore()
        self.history_store = history_store or GenerationHistoryStore()
        self._worker: GenerationWorker | None = None
        self._active_settings: GenerationSettings | None = None
        self._active_settings_payload: dict | None = None
        recovered = self.store.recover_and_validate()
        if recovered:
            self.log.emit(f"Đã khôi phục {recovered} mục hàng đợi sau lần đóng trước.")
        self._backfill_unit_counts()
        # Keep references to in-flight scan runnables so Qt does not collect them
        # mid-scan; each removes itself once it finishes.
        self._pending_scans: set[FunctionTask] = set()

    # --- Queue mutations ----------------------------------------------------

    def items(self) -> list[FileQueueItem]:
        return self.store.list_items()

    def add_paths(self, paths: list[Path]) -> None:
        """Scan and add on the calling thread (small, synchronous adds/tests)."""
        self._apply_scanned_sources(*scan_source_stats(paths))

    def add_paths_async(self, paths: list[Path]) -> None:
        """Scan sources off the GUI thread so large drops/pastes never lag.

        Reading text stats opens every file; doing that for hundreds of paths on
        the UI thread freezes the window. The scan runs in the thread pool and
        the store is mutated back on the GUI thread when it completes.
        """
        paths = list(paths)
        if not paths:
            return
        self.log.emit(f"Đang quét {len(paths)} đường dẫn nguồn…")
        task = FunctionTask(lambda: scan_source_stats(paths))

        def _completed(payload, runnable=task) -> None:
            self._pending_scans.discard(runnable)
            self._apply_scanned_sources(*payload)

        def _failed(message: str, runnable=task) -> None:
            self._pending_scans.discard(runnable)
            self.log.emit(f"Lỗi khi quét file nguồn: {message}")

        task.signals.completed.connect(_completed)
        task.signals.failed.connect(_failed)
        self._pending_scans.add(task)
        QThreadPool.globalInstance().start(task)

    def _apply_scanned_sources(
        self, sources: list[tuple[Path, int, int]], skipped: int
    ) -> None:
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
        self.add_paths_async(parse_path_text(text))

    def prepare_source_for_rerun(self, source_path: Path) -> FileQueueItem:
        """Add or reset one historical source so it is pending again."""
        path = Path(source_path).expanduser().resolve(strict=False)
        try:
            char_count, unit_count = source_text_stats(path)
        except Exception as error:
            raise OmniTtsError(f"Không đọc được file nguồn: {path}") from error
        item, added = self.store.add(path, char_count, unit_count)
        if item.status == FileQueueStatus.RUNNING:
            raise OmniTtsError("File này đang chạy trong hàng đợi.")
        if not added:
            self.store.reset([item.item_id])
            self.store.refresh_source_metadata(item.item_id, char_count, unit_count)
        restored = self.store.get(item.item_id)
        self.log.emit(
            f"Đã đưa {path.name} vào hàng đợi với trạng thái chờ chạy."
        )
        self.items_changed.emit()
        return restored

    def _backfill_unit_counts(self) -> None:
        """Populate the new statistic for queue rows created by older builds."""
        refreshed = 0
        for item in self.store.list_items():
            if item.unit_count >= 0 or item.status == FileQueueStatus.RUNNING:
                continue
            try:
                char_count, unit_count = source_text_stats(item.source_path)
            except Exception:
                continue
            self.store.refresh_source_metadata(item.item_id, char_count, unit_count)
            refreshed += 1
        if refreshed:
            self.log.emit(f"Đã cập nhật số đoạn cho {refreshed} file trong hàng đợi.")

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
        request = settings.to_request("x")
        payload = request.model_dump(mode="json")
        studio_selection = request.pronunciation
        snapshot_hashes: dict[tuple[bool, tuple[str, ...]], str] = {}
        fingerprints: dict[str, str] = {}
        for item in self.store.list_items():
            if item.status != FileQueueStatus.DONE:
                continue
            selection = self._pronunciation_selection(item, studio_selection)
            key = (selection.enabled, tuple(selection.preset_ids))
            if key not in snapshot_hashes:
                try:
                    analysis = self.context.controller.preview_pronunciation("", selection)
                    snapshot_hashes[key] = analysis.snapshot_hash
                except Exception as error:
                    snapshot_hashes[key] = f"unavailable:{key!r}"
                    self.log.emit(f"Không kiểm tra được preset cách đọc: {error}")
            fingerprints[item.item_id] = queue_settings_fingerprint(
                payload,
                snapshot_hashes[key],
            )
        changed = self.store.mark_settings_outdated_by_item(fingerprints)
        if changed:
            self.log.emit(f"{changed} file cần chạy lại do thiết lập thay đổi.")
            self.items_changed.emit()

    def set_pronunciation_binding(
        self,
        item_ids: list[str],
        *,
        mode: FileQueuePronunciationMode | str,
        preset_ids: list[str],
        studio_selection: PronunciationSelection,
    ) -> None:
        """Persist a row binding and scan exact matches for immediate review."""
        parsed_mode = FileQueuePronunciationMode(mode)
        changed = self.store.set_pronunciation_binding(
            item_ids,
            mode=parsed_mode,
            preset_ids=preset_ids,
        )
        scanned = 0
        failed = 0
        revised = 0
        for item_id in item_ids:
            try:
                item = self.store.get(item_id)
                selection = self._pronunciation_selection(item, studio_selection)
                text = read_source_text(item.source_path, preserve_higgs_tags=True)
                analysis = self.context.controller.preview_pronunciation(text, selection)
                invalidated = self.store.update_pronunciation_stats(
                    item_id,
                    term_count=analysis.term_count,
                    match_count=analysis.match_count,
                    conflict_count=analysis.conflict_count,
                    details=analysis_details(analysis, limit=20),
                    snapshot_hash=analysis.snapshot_hash,
                )
                revised += int(invalidated)
                scanned += 1
            except Exception as error:
                failed += 1
                self.log.emit(f"Không quét được cách đọc cho {item_id}: {error}")
        message = f"Đã quét cách đọc cho {scanned}/{len(item_ids)} mục."
        if changed:
            message += f" Đã đổi binding của {changed} mục."
        if revised:
            message += f" {revised} kết quả cần chạy lại do preset đã đổi."
        if failed:
            message += f" {failed} mục lỗi."
        self.log.emit(message)
        self.items_changed.emit()

    # --- Running the queue --------------------------------------------------

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run(self, scope: str, settings: GenerationSettings, selected_ids: list[str]) -> None:
        if self.is_running():
            self.log.emit("Hàng đợi đang chạy.")
            return
        tasks = self._tasks_for(scope, selected_ids, settings.to_request("x").pronunciation)
        if not tasks:
            self.log.emit("Không có file phù hợp để chạy.")
            return
        self._active_settings = settings
        self._active_settings_payload = settings.to_request("x").model_dump(mode="json")
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

    def _tasks_for(
        self,
        scope: str,
        selected_ids: list[str],
        studio_selection: PronunciationSelection,
    ) -> list[FileGenerationTask]:
        selected = set(selected_ids)
        retry_states = {
            FileQueueStatus.FAILED, FileQueueStatus.CANCELLED,
            FileQueueStatus.INTERRUPTED, FileQueueStatus.OUTDATED,
        }
        tasks: list[FileGenerationTask] = []
        for item in self.store.list_items():
            if item.status == FileQueueStatus.RUNNING:
                continue
            if scope == "selected" and item.item_id not in selected:
                continue
            if scope == "pending" and item.status != FileQueueStatus.PENDING:
                continue
            if scope == "failed" and item.status not in retry_states:
                continue
            override = None
            if item.pronunciation_mode != FileQueuePronunciationMode.INHERIT:
                override = self._pronunciation_selection(item, studio_selection)
            tasks.append(
                FileGenerationTask(
                    item_id=item.item_id,
                    source_path=item.source_path,
                    pronunciation=override,
                )
            )
        return tasks

    @staticmethod
    def _pronunciation_selection(
        item: FileQueueItem,
        studio_selection: PronunciationSelection,
    ) -> PronunciationSelection:
        if item.pronunciation_mode == FileQueuePronunciationMode.OFF:
            return PronunciationSelection(enabled=False)
        if item.pronunciation_mode == FileQueuePronunciationMode.PRESET:
            return PronunciationSelection(
                enabled=True,
                preset_ids=list(item.pronunciation_preset_ids),
            )
        return studio_selection

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
                fingerprint=(
                    queue_settings_fingerprint(
                        self._active_settings_payload,
                        event.result.pronunciation_snapshot_hash,
                    )
                    if self._active_settings_payload is not None
                    else ""
                ),
                output_manifest=manifest,
                duration_seconds=event.result.duration_seconds,
                detail=event.message or "Đã tạo audio.",
            )
            self.store.update_pronunciation_stats(
                event.item_id,
                term_count=event.result.pronunciation_term_count,
                match_count=event.result.pronunciation_match_count,
                conflict_count=event.result.pronunciation_conflict_count,
                details=_result_pronunciation_details(
                    event.result,
                    self.store.get(event.item_id).pronunciation_details,
                ),
                snapshot_hash=event.result.pronunciation_snapshot_hash,
                invalidate_completed=False,
            )
            self._record_history(event, HistoryStatus.DONE)
        elif event.status == FileQueueStatus.FAILED:
            self.store.mark_failed(event.item_id, event.error or event.message)
            self._record_history(event, HistoryStatus.FAILED)
        elif event.status == FileQueueStatus.CANCELLED:
            self.store.mark_cancelled(event.item_id)
            self._record_history(event, HistoryStatus.CANCELLED)
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
        self._active_settings = None
        self._active_settings_payload = None
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

    def _record_history(
        self, event: FileGenerationEvent, status: HistoryStatus
    ) -> None:
        settings = self._active_settings
        if settings is None:
            return
        item = self.store.get(event.item_id)
        self.history_store.record(
            mode="file",
            source_label=item.source_path.name,
            source_path=item.source_path,
            char_count=item.char_count,
            model_id=settings.model_id,
            provider_id=self.context.controller.provider_of_model(settings.model_id),
            status=status,
            result=event.result,
            settings_snapshot=settings.to_snapshot(),
            error=event.error or (event.message if status != HistoryStatus.DONE else ""),
        )
        self.history_changed.emit()


def _result_pronunciation_details(result, fallback: str = "") -> str:
    """Read the immutable core report so completed rows show the exact applied terms."""
    path = getattr(result, "pronunciation_report_path", None)
    if path is None:
        return fallback
    try:
        report = PronunciationReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return fallback
    return analysis_details(report, limit=20) or fallback


def scan_source_stats(
    paths: list[Path],
) -> tuple[list[tuple[Path, int, int]], int]:
    """Expand folders and read text stats. Pure/blocking — safe off the GUI thread.

    Returns ``(sources, skipped)`` where each source is ``(path, chars, units)``.
    """
    sources: list[tuple[Path, int, int]] = []
    skipped = 0
    for path in paths:
        for resolved in _expand(path):
            try:
                chars, units = source_text_stats(resolved)
            except Exception:
                skipped += 1
                continue
            sources.append((resolved, chars, units))
    return sources, skipped


def _expand(path: Path) -> list[Path]:
    if path.is_dir():
        found: list[Path] = []
        for ext in SUPPORTED_TEXT_EXTENSIONS:
            found.extend(sorted(path.rglob(f"*{ext}")))
        return found
    if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return [path]
    return []
