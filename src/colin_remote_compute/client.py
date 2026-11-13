"""Qt and MCP enqueue work here. Only the detached daemon executes jobs."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from filelock import FileLock, Timeout

from omni_tts_shared.errors import GenerationCancelled, GenerationError
from colin_colab_remote.settings import SettingsStore, data_root

from .context import managed_execution
from .store import ColabStore, TERMINAL
from .targets import pc_target, resolve_pc_pool, resolve_pc_profile


CPU_POOL_PROTOCOL = 1


def jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    return value


def should_manage(settings) -> bool:
    if settings.runtime_target != "remote" or managed_execution() is not None:
        return False
    return pc_target(settings) or (settings.model_id in {"vieneu_v3_turbo", "zerotts_202m_official"}
                                   and (getattr(settings, "remote_execution_kind", "") == "managed_colab"
                                        or SettingsStore().load().enabled))


def public_job(record: dict) -> dict:
    payload = record["payload"]
    settings = payload["settings"]
    summary = {"model_id": settings["model_id"], "output": {"directory": settings.get("output_dir")},
               "voice": {"mode": settings.get("voice_source_mode"), "voice_id": settings.get("speaker_id")}}
    if record["kind"] == "text":
        summary.update(text_length=len(payload["text"]), text_preview=payload["text"][:120])
    else:
        summary["source_files"] = [item["source_path"] for item in payload["tasks"]]
    target = payload.get("remote_target", {})
    if target.get("kind") == "existing_worker":
        profile = target["profile"]
        summary["execution"] = {"kind": "existing_worker", "backend": "cpu",
                                "worker_id": profile["worker_id"], "worker_name": profile["label"]}
    elif target.get("kind") == "cpu_pool":
        summary["execution"] = {"kind": "cpu_pool", "backend": "cpu", "worker_name": "Nhóm CPU",
                                "machines": [item["label"] for item in target["profiles"]], "limit": target["limit"]}
    return {key: record.get(key) for key in ("job_id", "kind", "status", "progress", "message", "error",
                                            "error_code", "created_at", "updated_at", "started_at", "finished_at", "result", "paused")} | {"request_summary": summary}


class ColabClient:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_root()
        self.store = ColabStore(self.directory)

    def configure(self, settings):
        from colin_colab_remote.autostart import configure_autostart
        SettingsStore(self.directory).save(settings)
        configure_autostart(self.directory, settings.enabled and settings.resume_at_logon)
        if settings.enabled:
            self.ensure_daemon()
        return settings.model_dump()

    def ensure_daemon(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.directory / "startup.lock"), timeout=10):
            probe = FileLock(str(self.directory / "supervisor.lock"))
            try:
                probe.acquire(timeout=0)
            except Timeout:
                return
            else:
                probe.release()
            python = Path(sys.executable)
            if os.name == "nt" and python.with_name("pythonw.exe").is_file():
                python = python.with_name("pythonw.exe")
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).resolve().parents[1]), env.get("PYTHONPATH", "")])
            options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
            log = self.directory / "supervisor.log"
            with log.open("ab") as stream:
                subprocess.Popen([str(python), "-m", "colin_remote_compute.daemon", "--data-dir", str(self.directory)],
                                 stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, env=env, **options)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    probe.acquire(timeout=0)
                except Timeout:
                    return
                else:
                    probe.release()
                time.sleep(0.1)
            raise GenerationError("Chưa khởi động được bộ điều phối Colab. Xem supervisor.log.")

    def submit(self, kind: str, payload: dict, request_key: str | None = None):
        settings = payload["settings"]
        is_pc = pc_target(settings)
        if not is_pc and not SettingsStore(self.directory).load().enabled:
            raise GenerationError("Bật Colab tự động trong bảng quản lý trước khi tạo job.")
        if is_pc:
            from omni_tts_core.model_registry import ModelRegistry
            from omni_tts_core.runtime_devices import supports_remote_cpu
            if (settings.remote_execution_backend or "cpu") != "cpu" or not supports_remote_cpu(ModelRegistry().get(settings.model_id)):
                raise GenerationError("Model chưa hỗ trợ CPU máy khác.")
            if settings.remote_execution_kind == "cpu_pool":
                profiles, limit = resolve_pc_pool()
                target = {"kind": "cpu_pool", "profiles": jsonable(profiles), "limit": limit}
            else:
                profile = resolve_pc_profile(settings.remote_worker_profile_id)
                target = {"kind": "existing_worker", "profile": jsonable(profile)}
        payload = jsonable(payload)
        if kind not in {"text", "files"} or (not is_pc and settings.model_id not in {"vieneu_v3_turbo", "zerotts_202m_official"}):
            raise GenerationError("Colab tự động hỗ trợ VieNeu v3 Turbo và ZeroTTS 202M Official.")
        if is_pc:
            payload["remote_target"] = target
        paths = [item["source_path"] for item in payload.get("tasks", [])]
        reference = payload["settings"].get("reference_audio_path")
        if reference:
            paths.append(reference)
        profile_id = payload["settings"].get("voice_profile_id")
        if profile_id:
            from omni_tts_core.model_registry import ModelRegistry
            from omni_tts_core.voice_profile_policy import VoiceProfilePolicy
            from omni_tts_core.voice_profiles import VoiceProfileManager
            profile = VoiceProfileManager().get_profile(profile_id)
            payload["voice_profile_snapshot"] = profile.model_dump(mode="json")
            selected = VoiceProfilePolicy(ModelRegistry()).resolve_audio_path(profile, payload["settings"]["model_id"])
            paths.append(str(selected))
        payload["input_hashes"] = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
        self.ensure_daemon()
        if is_pc and target["kind"] == "cpu_pool":
            deadline = time.monotonic() + 4
            while self.store.state("supervisor", {}).get("cpu_pool_protocol") != CPU_POOL_PROTOCOL:
                if time.monotonic() >= deadline:
                    raise GenerationError("Bộ điều phối nền cần cập nhật. Khởi động lại Windows để nạp bản mới.")
                time.sleep(0.1)
        return self.store.create(kind, payload, request_key)

    def control(self, job_id, action):
        self.ensure_daemon()
        return public_job(self.store.control(job_id, action))

    def release(self):
        self.store.set_state("release_requested", True)
        self.ensure_daemon()
        return {"status": "release_pending"}

    def status(self):
        beat = self.store.state("supervisor", {})
        return {"settings": SettingsStore(self.directory).load().model_dump(),
                "supervisor": {**beat, "online": time.time() - beat.get("heartbeat", 0) < 15},
                "runtime": self.store.state("runtime", {}),
                "cleanup_error": self.store.state("cleanup_error"),
                "jobs": [public_job(job) | {"verified_units": self.store.state(job["job_id"] + ":verified_units", 0)} for job in self.store.list()]}

    def _progress_message(self, record):
        status = record["status"]
        if status == "cancelling":
            return "Đang hủy tác vụ từ xa · chờ xác nhận từ bộ điều phối."
        if record["paused"] and status not in TERMINAL:
            return "Tác vụ đã tạm dừng · bấm Tiếp tục trong bảng quản lý để chạy tiếp."
        if str(record["message"] or "").strip():
            return record["message"]
        if status == "queued":
            ahead = self.store.queue_ahead(
                record["job_id"], allow_colab=SettingsStore(self.directory).load().enabled,
            )
            if ahead:
                message = f"Đã xếp hàng · {len(ahead)} tác vụ phía trước."
                active = next((job for job in ahead if job["status"] in {"running", "cancelling"}), None)
                if active and active["message"]:
                    message += " Tác vụ đang chạy: " + active["message"]
                return message
            return "Đã xếp hàng · đang chờ bộ điều phối nhận việc."
        return {
            "running": "Bộ điều phối đang chuẩn bị tác vụ tạo giọng.",
            "succeeded": "Audio đã hoàn tất.",
            "cancelled": "Đã hủy tác vụ tạo giọng.",
            "failed": "Tác vụ tạo giọng thất bại.",
            "waiting": "Tác vụ cần kiểm tra trong bảng quản lý trước khi tiếp tục.",
        }.get(status, "Đang kiểm tra trạng thái tác vụ tạo giọng.")

    def wait(self, job_id, *, progress_callback=None, cancel_event=None, file_event_callback=None):
        from omni_tts_core.progress import ProgressEvent
        last_update = None
        started = last_notice = time.monotonic()
        last_file_event = 0
        while True:
            record = self.store.get(job_id)
            if file_event_callback:
                from omni_tts_core.app_controller import FileGenerationEvent
                from omni_tts_core.file_queue import FileQueueStatus
                from omni_tts_shared.schemas import GenerateSpeechResult
                while True:
                    batch = self.store.file_events(job_id, last_file_event)
                    for sequence, item in batch:
                        last_file_event = sequence
                        item["source_path"] = Path(item["source_path"])
                        item["status"] = FileQueueStatus(item["status"])
                        if item.get("result"):
                            item["result"] = GenerateSpeechResult.model_validate(item["result"])
                        file_event_callback(FileGenerationEvent(**item))
                    if len(batch) < 200:
                        break
            message = self._progress_message(record)
            update = (record["status"], record["progress"], message)
            tick = time.monotonic()
            waiting_notice = record["status"] == "queued" and tick - last_notice >= 30
            if update != last_update or waiting_notice:
                last_update, last_notice = update, tick
                if progress_callback:
                    if waiting_notice:
                        message = f"Vẫn đang chờ sau {int(tick - started)} giây · {message}"
                    progress_callback(ProgressEvent(message, record["progress"], 100))
            if cancel_event is not None and cancel_event.is_set() and record["status"] not in TERMINAL:
                self.store.control(job_id, "cancel")
            if record["status"] == "succeeded":
                return record["result"]
            if record["status"] == "cancelled":
                raise GenerationCancelled(record["message"])
            if record["status"] in {"failed", "waiting"}:
                raise GenerationError(record["error"] or record["message"])
            time.sleep(0.5)


def generate_text(text, settings, progress_callback=None, cancel_event=None):
    from omni_tts_shared.schemas import GenerateSpeechResult
    client = ColabClient()
    record = client.submit("text", {"text": text, "settings": settings})
    result = client.wait(record["job_id"], progress_callback=progress_callback, cancel_event=cancel_event)
    return GenerateSpeechResult.model_validate(result)


def generate_files(tasks, settings, progress_callback=None, file_event_callback=None, cancel_event=None):
    from omni_tts_core.app_controller import FileGenerationOutcome, FileGenerationTask
    from omni_tts_core.file_queue import FileQueueStatus
    from omni_tts_shared.schemas import GenerateSpeechResult
    normalized = [task if isinstance(task, FileGenerationTask) else FileGenerationTask(task[0], task[1]) for task in tasks]
    client = ColabClient()
    record = client.submit("files", {"tasks": normalized, "settings": settings})
    result = client.wait(record["job_id"], progress_callback=progress_callback, cancel_event=cancel_event,
                         file_event_callback=file_event_callback)
    outcomes = []
    for item in result["files"]:
        outcomes.append(FileGenerationOutcome(item_id=item["item_id"], source_path=Path(item["source_path"]),
            status=FileQueueStatus(item["status"]), result=GenerateSpeechResult.model_validate(item["result"]) if item["result"] else None,
            error=item["error"]))
    return outcomes
