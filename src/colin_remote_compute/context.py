"""Durable remote inference context, scoped to the supervisor job thread."""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from contextvars import ContextVar
from pathlib import Path

from omni_tts_shared.errors import GenerationCancelled, GenerationError

from .broker.models import RemoteJobStatus, TERMINAL_REMOTE_JOB_STATUSES
from .pc_lifecycle import PcWorkerUnavailable


_execution = ContextVar("colin_colab_execution", default=None)


def managed_execution():
    return _execution.get()


class ManagedExecution:
    def __init__(self, store, job_id: str, lifecycle, *, verified_lock=None):
        self.store, self.job_id, self.lifecycle = store, job_id, lifecycle
        self.document = lifecycle.document
        self.units = store.directory / "artifacts" / job_id
        self.units.mkdir(parents=True, exist_ok=True)
        self._active_broker_job = None
        self.source_key = "text"
        self._calls = 0
        self.verified_lock = verified_lock or threading.Lock()

    def next_call_id(self):
        self._calls += 1
        return f"{self.job_id}:{self.source_key}:{self._calls}"

    def begin_source(self, source_key):
        self.source_key, self._calls = source_key, 0

    def check(self, cancel_event=None):
        job = self.store.get(self.job_id)
        if job["cancel_requested"] or (cancel_event is not None and cancel_event.is_set()):
            raise GenerationCancelled("Đã yêu cầu hủy job từ xa.")
        if not getattr(self.lifecycle, "is_existing_worker", False) and self.store.state("release_requested", False):
            raise GenerationCancelled("Đã yêu cầu dừng và giải phóng runtime Colab.")
        if self.lifecycle.expired():
            raise GenerationError("Đã đến trần thời gian runtime. Tiến độ đã lưu.")

    def status(self, message: str):
        previous = self.store.get(self.job_id)
        if previous["message"] != message:
            self.store.update(self.job_id, message=message)

    def freeze(self, key, produce):
        state_key = f"{self.job_id}:prepared:{key}"
        value = self.store.state(state_key)
        if value is None:
            value = produce()
            self.store.set_state(state_key, value)
        return value

    def cache_paths(self, request, destination: Path, *, is_pc: bool):
        excluded = {"client_job_id", "inference_unit_id", "idempotency_key", "metadata"}
        if not is_pc:
            # Old Colab checkpoints were computed before these optional fields existed.
            excluded.update({"segments", "execution_backend", "model_revision"})
        payload = request.model_dump(mode="json", exclude=excluded)
        payload["position"] = [request.client_job_id, request.inference_unit_id]
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cache = self.units / (digest + destination.suffix)
        proof = cache.with_suffix(cache.suffix + ".sha256")
        return digest, cache, proof

    @staticmethod
    def copy_verified(cache, proof, destination):
        if cache.is_file() and proof.is_file() and hashlib.sha256(cache.read_bytes()).hexdigest() == proof.read_text():
            shutil.copyfile(cache, destination)
            return True
        return False

    def execute(self, request, destination: Path, *, cancel_event=None, reference_audio=None):
        self.check(cancel_event)
        while self.store.get(self.job_id)["paused"]:
            self.status("Đã tạm dừng cấp đoạn mới")
            self.check(cancel_event)
            time.sleep(0.5)
        is_pc = getattr(self.lifecycle, "is_existing_worker", False)
        if is_pc:
            request = self.lifecycle.bind(request, lambda: self.check(cancel_event), self.status)
        digest, cache, proof = self.cache_paths(request, destination, is_pc=is_pc)
        if self.copy_verified(cache, proof, destination):
            return
        if not is_pc:
            self.lifecycle.ensure(request.model_id, lambda: self.check(cancel_event), self.status)
        attempt = self.store.state(f"{self.job_id}:attempt:{digest}", 0)
        key = f"{self.job_id}:{digest}:{attempt}"
        client = self.lifecycle.broker
        if reference_audio is not None and not is_pc:
            client.ensure_reference_audio(reference_audio)
        # The same logical unit keeps its key across client disconnects and restarts.
        remote = request.model_copy(update={"client_job_id": self.job_id, "inference_unit_id": digest,
                                            "idempotency_key": key})
        try:
            job = client.get_job_by_idempotency(key)
        except GenerationError as error:
            if "404" not in str(error):
                raise
            if is_pc:
                self.lifecycle.before_submit(remote, self.status)
                if reference_audio is not None:
                    client.ensure_reference_audio(reference_audio)
                self.check(cancel_event)
            try:
                job = client.submit(remote, worker_id=self.lifecycle.profile.worker_id)
            except GenerationError as submit_error:
                try:
                    job = client.get_job_by_idempotency(key)
                except GenerationError:
                    raise submit_error from None
        if is_pc:
            self.lifecycle.remember(key)
        self._active_broker_job = job.job_id
        try:
            queue_deadline = time.monotonic() + 60
            while job.status not in TERMINAL_REMOTE_JOB_STATUSES:
                try:
                    self.check(cancel_event)
                except (GenerationCancelled, GenerationError):
                    if is_pc:
                        self.lifecycle.cancel_pending()
                        raise
                    client.cancel(job.job_id)
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        job = client.get_job(job.job_id)
                        if job.status in TERMINAL_REMOTE_JOB_STATUSES:
                            break
                        time.sleep(0.5)
                    if job.status not in TERMINAL_REMOTE_JOB_STATUSES:
                        self.lifecycle.release()
                    raise
                if is_pc and job.status == RemoteJobStatus.QUEUED and time.monotonic() >= queue_deadline:
                    raise GenerationError("Máy CPU chưa nhận đoạn này. Bấm Tiếp tục để đối soát khi máy sẵn sàng.")
                time.sleep(0.5)
                job = client.get_job(job.job_id)
            if job.status == RemoteJobStatus.CANCELLED:
                if is_pc:
                    self.lifecycle.clear()
                    self.store.set_state(f"{self.job_id}:attempt:{digest}", attempt + 1)
                    self.check(cancel_event)
                    if getattr(self.lifecycle, "pool_slot", False):
                        raise PcWorkerUnavailable("Đoạn đã dừng trên máy CPU.")
                    raise GenerationError("Đoạn đã dừng trên máy CPU. Tiếp tục để chạy phần còn thiếu.")
                raise GenerationCancelled("Broker đã xác nhận hủy đoạn Colab.")
            if job.status != RemoteJobStatus.SUCCEEDED:
                # The failed attempt is terminal and reconciled. A future explicit
                # resume can use a new key without re-running verified units.
                self.store.set_state(f"{self.job_id}:attempt:{digest}", attempt + 1)
                if is_pc:
                    self.lifecycle.clear()
                    if getattr(self.lifecycle, "pool_slot", False) and job.retryable:
                        raise PcWorkerUnavailable(job.error or "Máy CPU chưa trả kết quả.")
                raise GenerationError(getattr(job, "error", "") or "Đoạn từ xa thất bại. Các đoạn đã xác minh được giữ.")
            client.download_result(job, cache)
            proof.write_text(hashlib.sha256(cache.read_bytes()).hexdigest())
            shutil.copyfile(cache, destination)
            with self.verified_lock:
                verified = len(list(self.units.glob("*.sha256")))
                self.store.set_state(self.job_id + ":verified_units", verified)
            if is_pc:
                self.lifecycle.clear()
        finally:
            self._active_broker_job = None

    def __enter__(self):
        self._token = _execution.set(self)
        return self

    def __exit__(self, *_):
        _execution.reset(self._token)
