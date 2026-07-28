"""Persistent, UI-agnostic history for completed generation attempts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_core.paths import ensure_dir
from omni_tts_core.ui_presenters.results import result_output_manifest
from omni_tts_shared.schemas import GenerateSpeechResult


class HistoryStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


HISTORY_STATUS_LABELS = {
    HistoryStatus.DONE: "Thành công",
    HistoryStatus.FAILED: "Lỗi",
    HistoryStatus.CANCELLED: "Đã hủy",
}


@dataclass(frozen=True)
class GenerationHistoryEntry:
    history_id: str
    mode: str
    source_label: str
    source_path: Path | None
    char_count: int
    model_id: str
    provider_id: str
    status: HistoryStatus
    duration_seconds: float
    output_manifest: FileQueueOutputManifest
    error: str
    created_at: str


class GenerationHistoryStore:
    """Append-only generation history kept separately from the live queue."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("config") / "generation_history.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record(
        self,
        *,
        mode: str,
        source_label: str,
        char_count: int,
        model_id: str,
        provider_id: str,
        status: HistoryStatus,
        source_path: Path | None = None,
        result: GenerateSpeechResult | None = None,
        error: str = "",
    ) -> GenerationHistoryEntry:
        manifest = result_output_manifest(result) if result is not None else FileQueueOutputManifest()
        entry = GenerationHistoryEntry(
            history_id=uuid4().hex,
            mode=mode,
            source_label=source_label.strip() or ("Văn bản trực tiếp" if mode == "text" else "File"),
            source_path=source_path,
            char_count=max(0, int(char_count)),
            model_id=model_id,
            provider_id=provider_id,
            status=status,
            duration_seconds=max(0.0, float(result.duration_seconds if result is not None else 0.0)),
            output_manifest=manifest,
            error=str(error or ""),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO generation_history (
                    history_id, mode, source_label, source_path, char_count,
                    model_id, provider_id, status, duration_seconds,
                    output_manifest_json, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.history_id,
                    entry.mode,
                    entry.source_label,
                    str(entry.source_path) if entry.source_path else "",
                    entry.char_count,
                    entry.model_id,
                    entry.provider_id,
                    entry.status.value,
                    entry.duration_seconds,
                    entry.output_manifest.to_json_text(),
                    entry.error,
                    entry.created_at,
                ),
            )
        return entry

    def list_entries(self, *, limit: int = 2000) -> list[GenerationHistoryEntry]:
        safe_limit = max(1, min(10000, int(limit)))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM generation_history
                ORDER BY created_at DESC, history_id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def delete(self, history_ids: list[str]) -> int:
        ids = list(dict.fromkeys(value for value in history_ids if value))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM generation_history WHERE history_id IN ({placeholders})",
                tuple(ids),
            )
            return cursor.rowcount

    def clear(self) -> int:
        with self._connect() as connection:
            return connection.execute("DELETE FROM generation_history").rowcount

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_history (
                    history_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    source_path TEXT NOT NULL DEFAULT '',
                    char_count INTEGER NOT NULL DEFAULT 0,
                    model_id TEXT NOT NULL DEFAULT '',
                    provider_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    output_manifest_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_generation_history_created "
                "ON generation_history(created_at DESC)"
            )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> GenerationHistoryEntry:
        try:
            status = HistoryStatus(row["status"])
        except ValueError:
            status = HistoryStatus.FAILED
        source_text = str(row["source_path"] or "").strip()
        return GenerationHistoryEntry(
            history_id=row["history_id"],
            mode=row["mode"],
            source_label=row["source_label"],
            source_path=Path(source_text) if source_text else None,
            char_count=int(row["char_count"] or 0),
            model_id=row["model_id"],
            provider_id=row["provider_id"],
            status=status,
            duration_seconds=float(row["duration_seconds"] or 0.0),
            output_manifest=FileQueueOutputManifest.from_json_text(
                row["output_manifest_json"]
            ),
            error=row["error"],
            created_at=row["created_at"],
        )
