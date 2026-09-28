from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable, Protocol

from omni_tts_shared.errors import GenerationCancelled, GenerationError

from .models import (
    RemoteJobStatus,
    RemoteTtsJob,
    RemoteTtsRequest,
    WorkerProfile,
    WorkerRecord,
)
from .profiles import WorkerProfileDocument


@dataclass(frozen=True)
class FailoverDecision:
    profile: WorkerProfile
    requires_confirmation: bool


@dataclass(frozen=True)
class RemoteExecutionOutcome:
    destination: Path
    initial_profile_id: str
    final_profile_id: str
    attempted_profile_ids: tuple[str, ...]
    failover_reasons: tuple[str, ...]


class BrokerClientProtocol(Protocol):
    def list_workers(self) -> list[WorkerRecord]: ...
    def submit(
        self, request: RemoteTtsRequest, *, worker_id: str = ""
    ) -> RemoteTtsJob: ...
    def get_job_by_idempotency(self, idempotency_key: str) -> RemoteTtsJob: ...
    def wait_for_terminal(
        self,
        job_id: str,
        *,
        cancel_event: Event | None = None,
    ) -> RemoteTtsJob: ...
    def download_result(self, job: RemoteTtsJob, destination: Path) -> Path: ...


ConfirmSwitch = Callable[[WorkerProfile, WorkerProfile, str], bool]
StatusCallback = Callable[[str], None]


class RemoteComputeCoordinator:
    def __init__(
        self,
        document: WorkerProfileDocument,
        *,
        client_factory: Callable[[WorkerProfile], BrokerClientProtocol],
        confirm_switch: ConfirmSwitch | None = None,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self.document = document
        self.client_factory = client_factory
        self.confirm_switch = confirm_switch
        self.status_callback = status_callback

    def execute(
        self,
        request: RemoteTtsRequest,
        destination: Path,
        *,
        cancel_event: Event | None = None,
    ) -> RemoteExecutionOutcome:
        current = self._selected_profile()
        initial_profile_id = current.profile_id
        attempted: list[str] = []
        failed: set[str] = set()
        reasons: list[str] = []
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled("Đã hủy tác vụ remote compute.")
            attempted.append(current.profile_id)
            client = self.client_factory(current)
            workers = client.list_workers()
            record = next(
                (
                    item
                    for item in workers
                    if item.capabilities.worker_id == current.worker_id
                ),
                None,
            )
            if record is None or not _is_online(record, datetime.now(timezone.utc), 120.0):
                reason = f"Worker {current.label} đang offline"
            elif not any(
                model.model_id == request.model_id
                for model in record.capabilities.models
            ):
                reason = f"Worker {current.label} không hỗ trợ {request.model_id}"
            else:
                attempt_request = request.model_copy(
                    update={
                        "idempotency_key": (
                            f"{request.idempotency_key}:{current.profile_id}"
                        )
                    }
                )
                self._status(f"Đang gửi tới {current.label}")
                job = self._submit_reconciled(client, attempt_request, current)
                terminal = client.wait_for_terminal(
                    job.job_id, cancel_event=cancel_event
                )
                if terminal.status == RemoteJobStatus.SUCCEEDED:
                    path = client.download_result(terminal, destination)
                    return RemoteExecutionOutcome(
                        destination=path,
                        initial_profile_id=initial_profile_id,
                        final_profile_id=current.profile_id,
                        attempted_profile_ids=tuple(attempted),
                        failover_reasons=tuple(reasons),
                    )
                if terminal.status == RemoteJobStatus.CANCELLED:
                    raise GenerationCancelled("Remote job đã bị hủy.")
                reason = terminal.error or f"Worker {current.label} xử lý thất bại"
                if not terminal.retryable:
                    raise GenerationError(reason)

            failed.add(current.profile_id)
            reasons.append(reason)
            decision = choose_failover(
                self.document,
                workers,
                model_id=request.model_id,
                failed_profile_ids=failed,
            )
            if decision is None:
                raise GenerationError(
                    f"Không còn worker online phù hợp sau lỗi: {reason}"
                )
            if decision.requires_confirmation:
                if self.confirm_switch is None or not self.confirm_switch(
                    current, decision.profile, reason
                ):
                    raise GenerationError(
                        f"Đã dừng vì không chuyển worker sau lỗi: {reason}"
                    )
            self._status(
                f"Chuyển từ {current.label} sang {decision.profile.label}: {reason}"
            )
            current = decision.profile

    def _selected_profile(self) -> WorkerProfile:
        selected_id = self.document.selection.selected_profile_id
        profile = next(
            (
                item
                for item in self.document.profiles
                if item.profile_id == selected_id and item.enabled
            ),
            None,
        )
        if profile is None:
            raise GenerationError("Chưa chọn worker remote đang bật.")
        return profile

    def _submit_reconciled(
        self,
        client: BrokerClientProtocol,
        request: RemoteTtsRequest,
        profile: WorkerProfile,
    ) -> RemoteTtsJob:
        try:
            return client.submit(request, worker_id=profile.worker_id)
        except GenerationError as submit_error:
            try:
                return client.get_job_by_idempotency(request.idempotency_key)
            except Exception as reconcile_error:
                raise GenerationError(
                    "Không xác định được broker đã nhận job hay chưa; "
                    "Studio dừng để tránh tạo audio trùng."
                ) from reconcile_error

    def _status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)


def choose_failover(
    document: WorkerProfileDocument,
    workers: list[WorkerRecord],
    *,
    model_id: str,
    failed_profile_ids: set[str],
    now: datetime | None = None,
    stale_after_seconds: float = 120.0,
) -> FailoverDecision | None:
    policy = document.selection.switch_policy
    if policy == "selected_only":
        return None
    current_time = now or datetime.now(timezone.utc)
    records = {worker.capabilities.worker_id: worker for worker in workers}
    for profile in _fallback_order(document):
        if not profile.enabled or profile.profile_id in failed_profile_ids:
            continue
        worker = records.get(profile.worker_id)
        if worker is None or not _is_online(worker, current_time, stale_after_seconds):
            continue
        if not any(item.model_id == model_id for item in worker.capabilities.models):
            continue
        return FailoverDecision(
            profile=profile,
            requires_confirmation=policy == "ask_before_switch",
        )
    return None


def _fallback_order(document: WorkerProfileDocument) -> list[WorkerProfile]:
    profiles = list(document.profiles)
    selected = document.selection.selected_profile_id
    selected_index = next(
        (index for index, profile in enumerate(profiles) if profile.profile_id == selected),
        -1,
    )
    if selected_index < 0:
        return profiles
    return profiles[selected_index + 1 :] + profiles[: selected_index + 1]


def _is_online(
    worker: WorkerRecord, now: datetime, stale_after_seconds: float
) -> bool:
    try:
        last_seen = datetime.fromisoformat(worker.last_seen_at)
    except ValueError:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return 0 <= (now - last_seen).total_seconds() <= stale_after_seconds
