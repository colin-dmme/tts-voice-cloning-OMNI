from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator
from uuid import uuid4

from omni_tts_core.paths import ensure_dir


class FileQueueStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    OUTDATED = "outdated"


STATUS_LABELS = {
    FileQueueStatus.PENDING: "Chờ chạy",
    FileQueueStatus.RUNNING: "Đang chạy",
    FileQueueStatus.DONE: "Thành công",
    FileQueueStatus.FAILED: "Lỗi",
    FileQueueStatus.CANCELLED: "Đã hủy",
    FileQueueStatus.INTERRUPTED: "Gián đoạn",
    FileQueueStatus.OUTDATED: "Cần chạy lại",
}


@dataclass(frozen=True)
class FileQueueOutputManifest:
    split_output_dirs: tuple[Path, ...] = ()
    split_audio_paths: tuple[Path, ...] = ()
    merged_audio_path: Path | None = None
    srt_paths: tuple[Path, ...] = ()
    job_dir: Path | None = None

    @classmethod
    def from_flat_paths(cls, paths: Iterable[Path]) -> "FileQueueOutputManifest":
        audio_paths = _unique_paths(
            path for path in paths if Path(path).suffix.lower() in {".wav", ".mp3"}
        )
        srt_paths = _unique_paths(path for path in paths if Path(path).suffix.lower() == ".srt")
        merged_audio_path = _merged_audio_from_flat_paths(audio_paths)
        split_audio_paths = tuple(path for path in audio_paths if path != merged_audio_path)
        split_output_dirs = _unique_paths(path.parent for path in split_audio_paths)
        return cls(
            split_output_dirs=split_output_dirs,
            split_audio_paths=split_audio_paths,
            merged_audio_path=merged_audio_path,
            srt_paths=srt_paths,
        )

    @classmethod
    def from_json_text(cls, value: str | None) -> "FileQueueOutputManifest":
        if not value:
            return cls()
        try:
            data = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            split_output_dirs=_path_tuple(data.get("split_output_dirs")),
            split_audio_paths=_path_tuple(data.get("split_audio_paths")),
            merged_audio_path=_optional_path(data.get("merged_audio_path")),
            srt_paths=_path_tuple(data.get("srt_paths")),
            job_dir=_optional_path(data.get("job_dir")),
        )

    def is_empty(self) -> bool:
        return not (
            self.split_output_dirs
            or self.split_audio_paths
            or self.merged_audio_path
            or self.srt_paths
            or self.job_dir
        )

    def paths_for(self, kind: str) -> tuple[Path, ...]:
        if kind == "all":
            return _unique_paths(
                [
                    *self.split_output_dirs,
                    self.merged_audio_path,
                    *self.srt_paths,
                ]
            )
        if kind == "split_dirs":
            return self.split_output_dirs
        if kind == "split_audio":
            return self.split_audio_paths
        if kind == "merged_audio":
            return (self.merged_audio_path,) if self.merged_audio_path else ()
        if kind == "srt":
            return self.srt_paths
        return ()

    def to_json_text(self) -> str:
        return json.dumps(
            {
                "split_output_dirs": [str(path) for path in self.split_output_dirs],
                "split_audio_paths": [str(path) for path in self.split_audio_paths],
                "merged_audio_path": str(self.merged_audio_path) if self.merged_audio_path else "",
                "srt_paths": [str(path) for path in self.srt_paths],
                "job_dir": str(self.job_dir) if self.job_dir else "",
            },
            ensure_ascii=False,
        )


@dataclass
class FileQueueItem:
    item_id: str
    source_path: Path
    path_key: str
    char_count: int
    status: FileQueueStatus = FileQueueStatus.PENDING
    progress_percent: float = 0.0
    attempt_count: int = 0
    last_error: str = ""
    status_detail: str = ""
    job_id: str = ""
    output_paths: tuple[Path, ...] = ()
    output_manifest: FileQueueOutputManifest = field(default_factory=FileQueueOutputManifest)
    settings_fingerprint: str = ""
    source_signature: str = ""
    position: int = 0
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


def path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False)).casefold()


def source_signature(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return ""
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def settings_fingerprint(payload: Any) -> str:
    normalized = _json_value(payload)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FileQueueStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_dir("config") / "file_queue.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_items(self) -> list[FileQueueItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM file_queue ORDER BY position, created_at, item_id"
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def add(self, source_path: Path, char_count: int) -> tuple[FileQueueItem, bool]:
        normalized = source_path.expanduser().resolve(strict=False)
        key = path_key(normalized)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM file_queue WHERE path_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                return self._row_to_item(existing), False
            position = int(
                connection.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM file_queue"
                ).fetchone()[0]
            )
            item = FileQueueItem(
                item_id=uuid4().hex,
                source_path=normalized,
                path_key=key,
                char_count=char_count,
                source_signature=source_signature(normalized),
                position=position,
                created_at=_now(),
            )
            connection.execute(
                """
                INSERT INTO file_queue (
                    item_id, source_path, path_key, char_count, status,
                    progress_percent, attempt_count, last_error, status_detail,
                    job_id, output_paths_json, output_manifest_json, settings_fingerprint,
                    source_signature, position, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._item_values(item),
            )
        return item, True

    def add_many(self, sources: Iterable[tuple[Path, int]]) -> tuple[list[FileQueueItem], int]:
        prepared: list[tuple[Path, str, int]] = []
        duplicates = 0
        seen_keys: set[str] = set()
        for source_path, char_count in sources:
            normalized = source_path.expanduser().resolve(strict=False)
            key = path_key(normalized)
            if key in seen_keys:
                duplicates += 1
                continue
            seen_keys.add(key)
            prepared.append((normalized, key, int(char_count)))
        if not prepared:
            return [], duplicates

        with self._connect() as connection:
            existing_keys: set[str] = set()
            keys = [key for _path, key, _count in prepared]
            for chunk in _chunks(keys, 900):
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT path_key FROM file_queue WHERE path_key IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
                existing_keys.update(str(row["path_key"]) for row in rows)

            position = int(
                connection.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM file_queue"
                ).fetchone()[0]
            )
            added: list[FileQueueItem] = []
            insert_values = []
            for normalized, key, char_count in prepared:
                if key in existing_keys:
                    duplicates += 1
                    continue
                item = FileQueueItem(
                    item_id=uuid4().hex,
                    source_path=normalized,
                    path_key=key,
                    char_count=char_count,
                    source_signature=source_signature(normalized),
                    position=position,
                    created_at=_now(),
                )
                position += 1
                added.append(item)
                insert_values.append(self._item_values(item))

            if insert_values:
                connection.executemany(
                    """
                    INSERT INTO file_queue (
                        item_id, source_path, path_key, char_count, status,
                        progress_percent, attempt_count, last_error, status_detail,
                        job_id, output_paths_json, output_manifest_json, settings_fingerprint,
                        source_signature, position, created_at, started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    insert_values,
                )
        return added, duplicates

    def mark_running(self, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE file_queue
                SET status = ?, progress_percent = 0, attempt_count = attempt_count + 1,
                    last_error = '', status_detail = 'Đang khởi tạo...',
                    job_id = '', output_paths_json = '[]', output_manifest_json = '{}',
                    source_signature = ?, started_at = ?, finished_at = ''
                WHERE item_id = ?
                """,
                (
                    FileQueueStatus.RUNNING.value,
                    source_signature(self.get(item_id).source_path),
                    _now(),
                    item_id,
                ),
            )

    def update_progress(self, item_id: str, progress_percent: float, detail: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE file_queue
                SET progress_percent = ?, status_detail = ?
                WHERE item_id = ?
                """,
                (max(0.0, min(100.0, progress_percent)), detail, item_id),
            )

    def mark_done(
        self,
        item_id: str,
        *,
        job_id: str,
        output_paths: Iterable[Path],
        fingerprint: str,
        output_manifest: FileQueueOutputManifest | None = None,
        detail: str = "Đã tạo audio.",
    ) -> None:
        outputs = [str(Path(path)) for path in output_paths]
        manifest = output_manifest or FileQueueOutputManifest.from_flat_paths(Path(path) for path in outputs)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE file_queue
                SET status = ?, progress_percent = 100, last_error = '',
                    status_detail = ?, job_id = ?, output_paths_json = ?,
                    output_manifest_json = ?,
                    settings_fingerprint = ?, finished_at = ?
                WHERE item_id = ?
                """,
                (
                    FileQueueStatus.DONE.value,
                    detail,
                    job_id,
                    json.dumps(outputs, ensure_ascii=False),
                    manifest.to_json_text(),
                    fingerprint,
                    _now(),
                    item_id,
                ),
            )

    def mark_failed(self, item_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE file_queue
                SET status = ?, last_error = ?, status_detail = ?,
                    finished_at = ?
                WHERE item_id = ?
                """,
                (
                    FileQueueStatus.FAILED.value,
                    error,
                    _short(error, 500),
                    _now(),
                    item_id,
                ),
            )

    def mark_cancelled(self, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE file_queue
                SET status = ?, status_detail = 'Đã hủy khi đang xử lý',
                    finished_at = ?
                WHERE item_id = ?
                """,
                (FileQueueStatus.CANCELLED.value, _now(), item_id),
            )

    def reset(self, item_ids: Iterable[str]) -> int:
        ids = _unique_ids(item_ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE file_queue
                SET status = ?, progress_percent = 0, last_error = '',
                    status_detail = '', job_id = '', output_paths_json = '[]',
                    output_manifest_json = '{{}}',
                    settings_fingerprint = '', started_at = '', finished_at = ''
                WHERE item_id IN ({placeholders}) AND status != ?
                """,
                (
                    FileQueueStatus.PENDING.value,
                    *ids,
                    FileQueueStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount

    def delete(self, item_ids: Iterable[str]) -> int:
        ids = _unique_ids(item_ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM file_queue WHERE item_id IN ({placeholders}) AND status != ?",
                (*ids, FileQueueStatus.RUNNING.value),
            )
            return cursor.rowcount

    def clear(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM file_queue WHERE status != ?",
                (FileQueueStatus.RUNNING.value,),
            )
            return cursor.rowcount

    def recover_and_validate(self) -> int:
        changed = 0
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE file_queue
                SET status = ?, status_detail = 'App đã đóng khi file đang chạy'
                WHERE status = ?
                """,
                (FileQueueStatus.INTERRUPTED.value, FileQueueStatus.RUNNING.value),
            )
            changed += cursor.rowcount

        for item in self.list_items():
            if item.status != FileQueueStatus.DONE:
                continue
            current_signature = source_signature(item.source_path)
            if not current_signature or current_signature != item.source_signature:
                self._mark_outdated(item.item_id, "File nguồn đã thay đổi hoặc không còn tồn tại")
                changed += 1
                continue
            if item.output_paths and not all(path.exists() for path in item.output_paths):
                self._mark_outdated(item.item_id, "Một hoặc nhiều file output không còn tồn tại")
                changed += 1
        return changed

    def mark_settings_outdated(self, fingerprint: str) -> int:
        if not fingerprint:
            return 0
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE file_queue
                SET status = ?, status_detail = 'Thiết lập tạo audio đã thay đổi'
                WHERE status = ? AND settings_fingerprint != ''
                    AND settings_fingerprint != ?
                """,
                (
                    FileQueueStatus.OUTDATED.value,
                    FileQueueStatus.DONE.value,
                    fingerprint,
                ),
            )
            return cursor.rowcount

    def get(self, item_id: str) -> FileQueueItem:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM file_queue WHERE item_id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            raise KeyError(item_id)
        return self._row_to_item(row)

    def _mark_outdated(self, item_id: str, detail: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE file_queue SET status = ?, status_detail = ? WHERE item_id = ?",
                (FileQueueStatus.OUTDATED.value, detail, item_id),
            )

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_queue (
                    item_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    path_key TEXT NOT NULL UNIQUE,
                    char_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    progress_percent REAL NOT NULL DEFAULT 0,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    status_detail TEXT NOT NULL DEFAULT '',
                    job_id TEXT NOT NULL DEFAULT '',
                    output_paths_json TEXT NOT NULL DEFAULT '[]',
                    output_manifest_json TEXT NOT NULL DEFAULT '{}',
                    settings_fingerprint TEXT NOT NULL DEFAULT '',
                    source_signature TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_queue_status ON file_queue(status)"
            )
            if "output_manifest_json" not in _column_names(connection, "file_queue"):
                connection.execute(
                    "ALTER TABLE file_queue ADD COLUMN output_manifest_json TEXT NOT NULL DEFAULT '{}'"
                )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> FileQueueItem:
        try:
            outputs = tuple(Path(value) for value in json.loads(row["output_paths_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            outputs = ()
        manifest = FileQueueOutputManifest.from_json_text(row["output_manifest_json"])
        if manifest.is_empty() and outputs:
            manifest = FileQueueOutputManifest.from_flat_paths(outputs)
        try:
            status = FileQueueStatus(row["status"])
        except ValueError:
            status = FileQueueStatus.PENDING
        return FileQueueItem(
            item_id=row["item_id"],
            source_path=Path(row["source_path"]),
            path_key=row["path_key"],
            char_count=int(row["char_count"]),
            status=status,
            progress_percent=float(row["progress_percent"]),
            attempt_count=int(row["attempt_count"]),
            last_error=row["last_error"],
            status_detail=row["status_detail"],
            job_id=row["job_id"],
            output_paths=outputs,
            output_manifest=manifest,
            settings_fingerprint=row["settings_fingerprint"],
            source_signature=row["source_signature"],
            position=int(row["position"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    @staticmethod
    def _item_values(item: FileQueueItem) -> tuple:
        return (
            item.item_id,
            str(item.source_path),
            item.path_key,
            item.char_count,
            item.status.value,
            item.progress_percent,
            item.attempt_count,
            item.last_error,
            item.status_detail,
            item.job_id,
            json.dumps([str(path) for path in item.output_paths], ensure_ascii=False),
            item.output_manifest.to_json_text(),
            item.settings_fingerprint,
            item.source_signature,
            item.position,
            item.created_at,
            item.started_at,
            item.finished_at,
        )


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _json_value(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _path_tuple(values: Any) -> tuple[Path, ...]:
    if not isinstance(values, list):
        return ()
    return _unique_paths(Path(value) for value in values if str(value or "").strip())


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _unique_paths(values: Iterable[Path | None]) -> tuple[Path, ...]:
    paths: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        path = Path(value)
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return tuple(paths)


def _merged_audio_from_flat_paths(audio_paths: tuple[Path, ...]) -> Path | None:
    if not audio_paths:
        return None
    if len(audio_paths) == 1:
        return audio_paths[0]
    for path in reversed(audio_paths):
        if not _looks_like_split_audio(path):
            return path
    return None


def _looks_like_split_audio(path: Path) -> bool:
    suffix = path.stem.rsplit("_", 1)[-1]
    return len(suffix) == 3 and suffix.isdigit()


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _unique_ids(item_ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(item_id) for item_id in item_ids if item_id))


def _chunks(values: list[str], size: int) -> Iterator[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _short(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"
