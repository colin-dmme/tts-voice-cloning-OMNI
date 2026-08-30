"""Durable MCP job metadata, separate from core audio artifacts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "interrupted"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class McpJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            now = now_utc()
            connection.execute(
                """UPDATE mcp_jobs
                   SET status='interrupted',
                       message='MCP server đã dừng trước khi tác vụ hoàn tất',
                       updated_at=?, finished_at=?
                   WHERE status IN ('queued', 'running', 'cancelling')""",
                (now, now),
            )

    def create(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid4().hex
        now = now_utc()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO mcp_jobs
                   (job_id, kind, status, progress, message, request_json, created_at, updated_at)
                   VALUES (?, ?, 'queued', 0, 'Đã xếp hàng', ?, ?, ?)""",
                (job_id, kind, json.dumps(payload, ensure_ascii=False), now, now),
            )
        return self.get(job_id)

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {
            "status", "progress", "message", "result_json", "error",
            "started_at", "finished_at",
        }
        invalid = set(changes) - allowed
        if invalid:
            raise ValueError(f"Job fields không hợp lệ: {sorted(invalid)}")
        changes["updated_at"] = now_utc()
        assignments = ", ".join(f"{key}=?" for key in changes)
        values = [changes[key] for key in changes]
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE mcp_jobs SET {assignments} WHERE job_id=?",
                values + [job_id],
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Không tìm thấy MCP job: {job_id}")
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Không tìm thấy MCP job: {job_id}")
        return _decode(row)

    def list(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM mcp_jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM mcp_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [_decode(row) for row in rows]


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["request"] = json.loads(item.pop("request_json"))
    result_json = item.pop("result_json")
    item["result"] = json.loads(result_json) if result_json else None
    return item