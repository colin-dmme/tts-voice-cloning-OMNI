"""One detached supervisor for CPU workers and Colab jobs."""
from __future__ import annotations

import argparse
import hashlib
import os
import threading
import time
import traceback
from pathlib import Path

from filelock import FileLock, Timeout

from omni_tts_shared.errors import GenerationCancelled, GenerationError, OmniTtsError
from omni_tts_shared.schemas import PC_EXECUTION_KINDS
from colin_colab_remote.google_mcp import GoogleColabProvider, ProviderError
from colin_colab_remote.lifecycle import ColabLifecycle
from colin_colab_remote.settings import SettingsStore, data_root

from .client import CPU_POOL_PROTOCOL, HYBRID_CPU_PROTOCOL, POSTPROCESSING_PROTOCOL, jsonable
from .broker.client import BrokerConnectionError
from .broker.models import WorkerProfile
from .context import ManagedExecution
from .pc_lifecycle import ExistingWorkerLifecycle, PcCancellationPending
from .pc_pool import CpuPoolLifecycle
from .store import ColabStore, now


def restore_settings(data):
    from omni_tts_core.ui_presenters.settings_state import GenerationSettings
    fields = dict(data)
    for key in ("output_dir", "reference_audio_path"):
        if fields.get(key):
            fields[key] = Path(fields[key])
    return GenerationSettings(**fields)


class ColabSupervisor:
    def __init__(self, directory: Path, *, provider_factory=GoogleColabProvider, controller_factory=None):
        self.directory, self.store = directory, ColabStore(directory)
        self.settings = SettingsStore(directory)
        self.provider_factory, self.controller_factory = provider_factory, controller_factory
        self._active = None
        self._stop = threading.Event()
        self._lifecycle = None

    def lifecycle(self):
        from omni_tts_core.paths import PROJECT_ROOT
        from .broker.profiles import WorkerProfileStore
        settings = self.settings.load()
        runtime = self.store.state("runtime", {})
        # The account that allocated a runtime must also release it, even if the
        # operator changed the selected account after a failure.
        account = runtime.get("account_id", settings.account_id)
        selected = settings.model_copy(update={"account_id": account})
        return ColabLifecycle(self.store, selected, self.provider_factory(self.directory, account),
                              WorkerProfileStore(PROJECT_ROOT / "config/remote_compute_workers.json"))

    def run(self):
        try:
            with FileLock(str(self.directory / "supervisor.lock"), timeout=0):
                self._loop()
        except Timeout:
            return

    def _loop(self):
        while not self._stop.is_set():
            self.store.set_state("supervisor", {"pid": os.getpid(), "heartbeat": time.time(),
                                                "cpu_pool_protocol": CPU_POOL_PROTOCOL,
                                                "hybrid_cpu_protocol": HYBRID_CPU_PROTOCOL,
                                                "postprocessing_protocol": POSTPROCESSING_PROTOCOL})
            if self._active and not self._active.is_alive():
                self._active = None
            if not self._active:
                runtime = self.store.state("runtime", {})
                release = self.store.state("release_requested", False)
                expired = runtime and time.time() >= runtime.get("deadline", 0)
                if release or expired or runtime.get("phase") == "release_pending":
                    try:
                        self.lifecycle().release()
                        self.store.set_state("release_requested", False)
                        self.store.set_state("cleanup_error", None)
                    except Exception:
                        self.store.set_state("cleanup_error", "Chưa xác nhận trả máy. Kết nối lại tài khoản và làm mới trạng thái.")
                    self._stop.wait(2)
                job = self.store.next_job(allow_colab=self.settings.load().enabled
                                          and not self.store.state("release_requested", False)
                                          and self.store.state("runtime", {}).get("phase") != "release_pending")
                if job:
                    self._active = threading.Thread(target=self.run_job, args=(job,), daemon=True)
                    self._active.start()
            self._stop.wait(0.5)

    def run_job(self, job):
        lifecycle = None
        is_pc = False
        try:
            payload, job_id = job["payload"], job["job_id"]
            target = payload.get("remote_target", {})
            is_pc = target.get("kind") in PC_EXECUTION_KINDS
            if target.get("kind") == "cpu_pool":
                profiles = [WorkerProfile.model_validate(item) for item in target["profiles"]]
                lifecycle = CpuPoolLifecycle(self.store, job_id, profiles, target["limit"],
                                             include_local=target.get("include_local", False))
            elif is_pc:
                lifecycle = ExistingWorkerLifecycle(self.store, job_id, WorkerProfile.model_validate(target["profile"]))
            if job["cancel_requested"]:
                if is_pc:
                    lifecycle.cancel_pending()
                raise GenerationCancelled("Đã hủy trước khi bắt đầu.")
            for path, digest in payload.get("input_hashes", {}).items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                    raise GenerationError("File nguồn hoặc mẫu giọng đã đổi. Tạo job mới cho nội dung mới.")
            if payload.get("voice_profile_snapshot"):
                from omni_tts_core.voice_profiles import VoiceProfileManager
                snapshot = payload["voice_profile_snapshot"]
                if VoiceProfileManager().get_profile(snapshot["profile_id"]).model_dump(mode="json") != snapshot:
                    raise GenerationError("Profile giọng đã đổi. Tạo job mới để dùng cấu hình giọng hiện tại.")
            settings = restore_settings(payload["settings"])
            postprocessing = self.store.state(job_id + ":postprocessing", {})
            if postprocessing.get("music") is not None:
                from omni_tts_shared.narrative_pacing import NarrativePacingOptions
                pacing = NarrativePacingOptions.model_validate(settings.narrative_pacing)
                settings.narrative_pacing = pacing.model_copy(update={
                    "music": pacing.music.model_validate(postprocessing["music"]),
                }).model_dump()
            if settings.output_dir is None:
                settings.output_dir = self.directory / "outputs" / job_id
            if not is_pc:
                lifecycle = self.lifecycle()
                if lifecycle.settings.account_id != self.settings.load().account_id:
                    lifecycle.release()
                    lifecycle = self.lifecycle()
            with ManagedExecution(self.store, job_id, lifecycle) as context:
                if self.controller_factory:
                    controller = self.controller_factory()
                else:
                    from omni_tts_core.app_controller import AppController
                    controller = AppController()
                progress = lambda event: self.store.update(job_id, progress=round(event.percent, 2), message=event.message)
                cancel = JobCancellation(self.store, job_id, include_colab_release=not is_pc)
                if job["kind"] == "text":
                    result = controller.generate_text(payload["text"], settings, progress_callback=progress, cancel_event=cancel)
                    result = jsonable(result)
                    self.store.set_state(job_id + ":output_proof", output_proof({"result": result}))
                else:
                    from omni_tts_core.app_controller import FileGenerationTask
                    from omni_tts_shared.pronunciation import PronunciationSelection
                    tasks = [FileGenerationTask(item["item_id"], Path(item["source_path"]),
                        PronunciationSelection.model_validate(item["pronunciation"]) if item.get("pronunciation") else None)
                        for item in payload["tasks"]]
                    outcomes = []
                    for index, task in enumerate(tasks):
                        context.check()
                        cached = self.store.state(job_id + ":file:" + task.item_id)
                        if cached and proof_valid(cached):
                            outcomes.append(cached["outcome"])
                            continue
                        context.begin_source(task.item_id)
                        completed = controller.generate_files([task], settings, progress_callback=progress, cancel_event=cancel,
                            file_event_callback=lambda event: self.store.add_file_event(job_id, jsonable(event)))
                        if len(completed) != 1 or completed[0].item_id != task.item_id:
                            raise GenerationError("Số file hoàn tất chưa khớp hàng đợi. Tiến độ đã xác minh được giữ.")
                        for item in completed:
                            outcome = jsonable(item)
                            outcomes.append(outcome)
                            if str(getattr(item.status, "value", item.status)) == "done" and not item.error and item.result:
                                self.store.set_state(job_id + ":file:" + task.item_id, output_proof(outcome))
                            else:
                                self.store.update(job_id, result={"files": outcomes})
                                raise GenerationError("File chưa có đủ kết quả tạo giọng đã xác minh.")
                        self.store.update(job_id, progress=(index + 1) / len(tasks) * 100)
                    result = {"files": outcomes}
                    if any(item["error"] for item in outcomes):
                        self.store.update(job_id, result=result)
                        raise GenerationError("Một số file chưa tạo xong. Các đoạn đã xác minh được giữ để tiếp tục.")
                self.store.complete(job_id, result)
        except PcCancellationPending as error:
            self.store.update(job["job_id"], status="cancelling", message=str(error))
            self._stop.wait(3)
        except GenerationCancelled as error:
            if is_pc and lifecycle.has_pending():
                # A cancellation at a boundary after reconnect still needs reconciliation.
                self.store.update(job["job_id"], status="cancelling", message="Đang đối soát lệnh hủy với broker.")
                return
            self.store.update(job["job_id"], status="cancelled", message=str(error), finished_at=now())
        except (ProviderError, BrokerConnectionError) as error:
            retries = self.store.state(job["job_id"] + ":network_retries", 0)
            retry = error.code in {"timeout", "unavailable", "broker_unavailable"} and retries < 3
            self.store.set_state(job["job_id"] + ":network_retries", retries + 1)
            self.store.wait_or_retry(job["job_id"], str(error), error.code, retry=retry)
            if retry:
                self._stop.wait(min(30, 5 * (retries + 1)))
        except (OmniTtsError, OSError, ValueError) as error:
            self.store.wait_or_retry(job["job_id"], str(error)[:400], "retry_required")
        except Exception:
            diagnostic = self.directory / "artifacts" / job["job_id"] / "error.log"
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            diagnostic.write_text(traceback.format_exc(), encoding="utf-8")
            self.store.wait_or_retry(job["job_id"], "Lỗi xử lý job từ xa. Kiểm tra cấu hình rồi bấm Tiếp tục.", "job_error")
        finally:
            if lifecycle and not is_pc and (self.settings.load().auto_release or self.store.state("release_requested", False)):
                try:
                    lifecycle.release()
                    self.store.set_state("release_requested", False)
                    self.store.set_state("cleanup_error", None)
                except Exception:
                    self.store.set_state("cleanup_error", "Chưa xác nhận trả runtime. Kiểm tra lại kết nối Google.")


def main():
    parser = argparse.ArgumentParser(description="Bộ điều phối job từ xa của Colin TTS Studio")
    parser.add_argument("--data-dir", type=Path, default=data_root())
    args = parser.parse_args()
    ColabSupervisor(args.data_dir).run()


class JobCancellation:
    def __init__(self, store, job_id, *, include_colab_release=True):
        self.store, self.job_id = store, job_id
        self.include_colab_release = include_colab_release

    def is_set(self):
        return bool(self.store.get(self.job_id)["cancel_requested"] or
                    (self.include_colab_release and self.store.state("release_requested", False)))

    def wait(self, timeout=None):
        deadline = time.monotonic() + (timeout if timeout is not None else 86400)
        while not self.is_set() and time.monotonic() < deadline:
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        return self.is_set()


def output_proof(outcome):
    result = outcome["result"]
    candidates = [result.get("audio_path"), result.get("srt_path"), *result.get("item_audio_paths", []), *result.get("item_srt_paths", [])]
    required = [*result.get("item_audio_paths", []), *result.get("item_srt_paths", [])]
    if result.get("srt_path"):
        required.append(result["srt_path"])
    if any(not Path(path).is_file() for path in required):
        raise GenerationError("Thiếu tệp đầu ra yêu cầu. Cần tiếp tục phần chưa hoàn tất.")
    hashes = {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in candidates if path and Path(path).is_file()}
    if not hashes:
        raise GenerationError("Chưa tìm thấy tệp audio đã hoàn tất.")
    return {"outcome": outcome, "hashes": hashes}


def proof_valid(record):
    try:
        return bool(record["hashes"]) and all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in record["hashes"].items())
    except OSError:
        return False


if __name__ == "__main__":
    main()
