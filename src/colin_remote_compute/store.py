"""Single durable queue shared by Qt, MCP and the Colab supervisor."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from omni_tts_shared.schemas import PC_EXECUTION_KINDS


TERMINAL = {"succeeded", "failed", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class ColabStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "jobs.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, request_key TEXT UNIQUE, fingerprint TEXT NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
                    error TEXT, error_code TEXT, result TEXT, paused INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    started_at TEXT, finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    time TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS file_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, kind: str, payload: dict, request_key: str | None = None) -> dict:
        fingerprint = hashlib.sha256(encode({"kind": kind, "payload": payload}).encode()).hexdigest()
        prefix = "cpu-job-" if payload.get("remote_target", {}).get("kind") in PC_EXECUTION_KINDS else "colab-"
        job_id, stamp = prefix + uuid4().hex, now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_key:
                previous = db.execute("SELECT * FROM jobs WHERE request_key=?", (request_key,)).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise ValueError("Khóa yêu cầu đã dùng cho nội dung khác.")
                    return self.decode(previous)
            db.execute("INSERT INTO jobs(job_id,request_key,fingerprint,kind,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,'queued',?,?)",
                       (job_id, request_key, fingerprint, kind, encode(payload), stamp, stamp))
        return self.get(job_id)

    @staticmethod
    def decode(row) -> dict:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        item["result"] = json.loads(item["result"]) if item["result"] else None
        return item

    def get(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("Không tìm thấy Colab job.")
        return self.decode(row)

    def list(self, limit: int = 30, status: str | None = None) -> list[dict]:
        with self.connect() as db:
            if status:
                rows = db.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, min(100, max(1, limit)))).fetchall()
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (min(100, max(1, limit)),)).fetchall()
        return [self.decode(row) for row in rows]

    def next_job(self, *, allow_colab: bool = True) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM jobs WHERE status IN ('queued','running','cancelling') AND paused=0
                   AND (? OR job_id LIKE 'cpu-job-%') ORDER BY created_at LIMIT 1""", (allow_colab,),
            ).fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running',started_at=COALESCE(started_at,?),updated_at=? WHERE job_id=?", (now(), now(), row["job_id"]))
        return self.get(row["job_id"]) if row else None

    def queue_ahead(self, job_id: str, *, allow_colab: bool = True) -> list[dict]:
        """Scheduler-eligible work ahead, without loading source text or settings."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT job_id,status,message FROM jobs
                   WHERE status IN ('queued','running','cancelling') AND paused=0
                   AND (? OR job_id LIKE 'cpu-job-%')
                   AND (created_at,rowid) < (SELECT created_at,rowid FROM jobs WHERE job_id=?)
                   ORDER BY created_at,rowid""", (allow_colab, job_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def update(self, job_id: str, **changes) -> dict:
        allowed = {"status", "progress", "message", "error", "error_code", "result", "started_at", "finished_at"}
        if not changes.keys() <= allowed:
            raise ValueError("Trường Colab job không hợp lệ.")
        if "result" in changes:
            changes["result"] = encode(changes["result"])
        changes["updated_at"] = now()
        with self.connect() as db:
            columns = ",".join(f"{key}=?" for key in changes)
            db.execute(f"UPDATE jobs SET {columns} WHERE job_id=?", [*changes.values(), job_id])
            if changes.get("message"):
                db.execute("INSERT INTO events(job_id,time,message) VALUES(?,?,?)", (job_id, now(), changes["message"]))
        return self.get(job_id)

    def control(self, job_id: str, action: str) -> dict:
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("Điều khiển Colab job không hợp lệ.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Không tìm thấy Colab job.")
            if row["status"] not in TERMINAL:
                if action == "cancel":
                    db.execute("UPDATE jobs SET cancel_requested=1,paused=0,status='cancelling',updated_at=? WHERE job_id=?", (now(), job_id))
                else:
                    db.execute("UPDATE jobs SET paused=?,status=CASE WHEN status='waiting' THEN 'queued' ELSE status END,updated_at=? WHERE job_id=?",
                               (action == "pause", now(), job_id))
        return self.get(job_id)

    def complete(self, job_id: str, result: dict) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Không tìm thấy Colab job.")
            status = "cancelled" if row["cancel_requested"] else "succeeded"
            stamp = now()
            db.execute("UPDATE jobs SET status=?,paused=0,progress=100,result=?,message=?,error=NULL,error_code=NULL,finished_at=?,updated_at=? WHERE job_id=?",
                       (status, encode(result), "Đã hủy, giữ kết quả đã xác minh" if row["cancel_requested"] else "Audio đã hoàn tất", stamp, stamp, job_id))
        return self.get(job_id)

    def wait_or_retry(self, job_id: str, error: str, code: str, *, retry: bool = False) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError("Không tìm thấy Colab job.")
            cancelled = bool(row["cancel_requested"])
            needs_cancel = cancelled and bool(self._pending_pc_units(db, job_id))
            status = "cancelling" if needs_cancel else "cancelled" if cancelled else "queued" if retry else "waiting"
            stamp = now()
            message = ("Đang đối soát lệnh hủy với broker" if needs_cancel else "Đã hủy job từ xa" if cancelled
                       else "Đang chờ thử lại kết nối broker" if retry else "Cần kiểm tra và bấm Tiếp tục")
            db.execute("UPDATE jobs SET status=?,message=?,error=?,error_code=?,updated_at=?,finished_at=? WHERE job_id=?",
                       (status, message, error, code, stamp, stamp if status == "cancelled" else None, job_id))
        return self.get(job_id)

    def state(self, key: str, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_state(self, key: str, value) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(value)))

    @staticmethod
    def _pending_pc_units(db, job_id):
        key = f"{job_id}:pc-pending"
        return [row[0] for row in db.execute(
            "SELECT key FROM state WHERE value!='null' AND (key=? OR key LIKE ?)", (key, key + ":%"),
        )]

    def pending_pc_units(self, job_id):
        with self.connect() as db:
            return self._pending_pc_units(db, job_id)

    def events(self, job_id: str, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT time,message FROM events WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, min(200, max(1, limit)))).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_file_event(self, job_id, payload):
        with self.connect() as db:
            db.execute("INSERT INTO file_events(job_id,payload) VALUES(?,?)", (job_id, encode(payload)))

    def file_events(self, job_id, after=0):
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM file_events WHERE job_id=? AND id>? ORDER BY id LIMIT 200", (job_id, after)).fetchall()
        return [(row["id"], json.loads(row["payload"])) for row in rows]
