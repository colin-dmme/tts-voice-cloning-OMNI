"""Resolve the pinned capabilities of an already enrolled CPU machine."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from omni_tts_shared.errors import GenerationError

from .broker.client import BrokerClient
from .broker.models import BrokerConnectionOptions, TERMINAL_REMOTE_JOB_STATUSES, WorkerProfile
from .broker.profiles import WorkerProfileDocument


class PcCancellationPending(GenerationError):
    """Keep the local job cancelling until the broker confirms termination."""


class PcWorkerUnavailable(GenerationError):
    """The unit can safely be reassigned after a rejected or terminal attempt."""


def broker_for(profile: WorkerProfile) -> BrokerClient:
    return BrokerClient(BrokerConnectionOptions(
        base_url=profile.broker_url, auth_env=profile.auth_env, auth_token_file=profile.auth_token_file,
        request_timeout_seconds=20, max_retries=0,
    ), no_redirect=True)


def supports_unit(model, request) -> bool:
    return (model.model_id == request.model_id and model.execution_backend == "cpu"
            and (not request.reference_audio_id or model.supports_profile_clone)
            and (not request.batch_texts or model.supports_batch)
            and (not request.segments or model.supports_segments))


class ExistingWorkerLifecycle:
    is_existing_worker = True

    def __init__(self, store, job_id: str, profile: WorkerProfile, *, unit: str = "", allowed=None, sample_rate=None):
        self.store, self.job_id, self.profile = store, job_id, profile
        self.document = WorkerProfileDocument(profiles=[profile])
        self.broker = broker_for(profile)
        self.pending_key = f"{job_id}:pc-pending" + (f":{unit}" if unit else "")
        self.pool_slot = bool(unit)
        self.allowed = allowed
        self.sample_rate = sample_rate

    def expired(self) -> bool:
        return False

    def bind(self, request, check, status):
        check()
        key = f"{self.job_id}:model:{request.model_id}"
        revision = self.store.state(key)
        if revision is None:
            revision = self._model(request, status).revision
            self.store.set_state(key, revision)
        return request.model_copy(update={"model_revision": revision, "execution_backend": "cpu"})

    def _model(self, request, status):
        name = self.profile.label
        device = next((row for row in self.broker.list_pc_devices()
                       if row.get("worker_id") == self.profile.worker_id), None)
        if device is None or device.get("revoked"):
            raise PcWorkerUnavailable(f"{name} chưa có quyền nhận việc. Ghép máy lại rồi bấm Tiếp tục.")
        if device.get("desired_state") != "running":
            raise PcWorkerUnavailable(f"{name} đang ngừng nhận việc. Bật nhận việc rồi bấm Tiếp tục.")
        record = next((row for row in self.broker.list_workers()
                       if row.capabilities.worker_id == self.profile.worker_id), None)
        if not record or record.capabilities.worker_type != "remote_pc" or not self._recent(device.get("last_seen_at")):
            raise PcWorkerUnavailable(f"{name} đang offline. Bật CPU worker rồi bấm Tiếp tục.")
        if device.get("observed_state") not in {"idle", "busy"}:
            raise PcWorkerUnavailable(f"{name} chưa sẵn sàng nhận việc. Kiểm tra trạng thái worker.")
        model = next((item for item in record.capabilities.models if supports_unit(item, request)), None)
        if model is None:
            raise PcWorkerUnavailable(f"{name} chưa sẵn sàng cho model hoặc tùy chọn giọng đã chọn.")
        if (request.model_revision and request.model_revision != model.revision
                or self.sample_rate is not None and self.sample_rate != model.sample_rate):
            raise PcWorkerUnavailable(f"Phiên bản model trên {name} đã thay đổi. Tạo job mới để dùng bản mới.")
        status(f"Đang gửi tới {name} · CPU")
        return model

    @staticmethod
    def _recent(stamp) -> bool:
        try:
            seen = datetime.fromisoformat(stamp)
            return 0 <= (datetime.now(timezone.utc) - seen).total_seconds() < 90
        except (TypeError, ValueError):
            return False

    def before_submit(self, request, status):
        self._model(request, status)
        if self.allowed and not self.allowed(self.profile):
            raise PcWorkerUnavailable(f"{self.profile.label} đã được bỏ khỏi nhóm chia tải.")
        self.store.set_state(self.pending_key, request.idempotency_key)

    def remember(self, key: str):
        self.store.set_state(self.pending_key, key)

    def clear(self):
        self.store.set_state(self.pending_key, None)

    def has_pending(self):
        return bool(self.store.state(self.pending_key))

    def cancel_pending(self, *, timeout: float = 15):
        cancel_pending_unit(self.store, self.broker, self.pending_key, timeout=timeout)


def cancel_pending_unit(store, broker, pending_key, *, timeout: float = 15):
    key = store.state(pending_key)
    if not key:
        return
    try:
        job = broker.get_job_by_idempotency(key)
    except GenerationError as error:
        if "HTTP 404:" in str(error):
            store.set_state(pending_key, None)
            return
        raise PcCancellationPending("Đang chờ kết nối broker để xác nhận hủy đoạn.") from error
    try:
        if job.status not in TERMINAL_REMOTE_JOB_STATUSES:
            job = broker.cancel(job.job_id)
        deadline = time.monotonic() + timeout
        while job.status not in TERMINAL_REMOTE_JOB_STATUSES and time.monotonic() < deadline:
            time.sleep(0.5)
            job = broker.get_job(job.job_id)
    except GenerationError as error:
        raise PcCancellationPending("Đang chờ kết nối broker để xác nhận hủy đoạn.") from error
    if job.status not in TERMINAL_REMOTE_JOB_STATUSES:
        raise PcCancellationPending("Đã gửi lệnh hủy. Đang chờ worker xác nhận.")
    store.set_state(pending_key, None)
