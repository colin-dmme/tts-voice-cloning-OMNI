"""Distribute one Studio job over enrolled CPU machines on the same broker."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace

from omni_tts_shared.errors import GenerationCancelled, GenerationError

from .broker.profiles import WorkerProfileDocument
from .context import ManagedExecution
from .pc_lifecycle import (
    ExistingWorkerLifecycle, PcWorkerUnavailable,
    broker_for, cancel_pending_unit, supports_unit,
)
from .targets import profile_store


class CpuPoolLifecycle:
    is_existing_worker = True
    is_cpu_pool = True

    def __init__(self, store, job_id, profiles, limit):
        self.store, self.job_id, self.profiles, self.limit = store, job_id, profiles, limit
        self.document = WorkerProfileDocument(profiles=profiles, cpu_pool_limit=limit)
        self.broker = broker_for(profiles[0])

    def expired(self):
        return False

    def has_pending(self):
        return bool(self.store.pending_pc_units(self.job_id))

    def cancel_pending(self):
        keys = self.store.pending_pc_units(self.job_id)
        if keys:
            # Issue all independent cancels promptly even if one worker is offline.
            with ThreadPoolExecutor(max_workers=min(self.limit, len(keys))) as executor:
                futures = [executor.submit(cancel_pending_unit, self.store, self.broker, key) for key in keys]
                for future in futures:
                    future.result()

    def _allowed(self, profile):
        return any(current.profile_id == profile.profile_id and current.worker_id == profile.worker_id
                   and current.broker_url == profile.broker_url and current.enabled and current.pool_enabled
                   for current in profile_store().load().profiles)

    def _groups(self, units):
        devices = {row["worker_id"]: row for row in self.broker.list_pc_devices()
                   if not row.get("revoked") and row.get("desired_state") == "running"
                   and row.get("observed_state") in {"idle", "busy"}
                   and ExistingWorkerLifecycle._recent(row.get("last_seen_at"))}
        workers = {row.capabilities.worker_id: row.capabilities for row in self.broker.list_workers()
                   if row.capabilities.worker_type == "remote_pc"}
        groups = defaultdict(list)
        for profile in self.profiles:
            worker = workers.get(profile.worker_id)
            if worker is None or profile.worker_id not in devices or not self._allowed(profile):
                continue
            model = next((item for item in worker.models if item.revision
                          and all(supports_unit(item, unit.request) for unit in units)), None)
            if model is not None:
                groups[(model.revision, model.sample_rate)].append(profile)
        return groups

    def dispatch(self, context, units):
        if not units:
            return
        cancel_event = units[0].cancel_event
        context.check(cancel_event)
        model_id = units[0].request.model_id
        group_key = f"{self.job_id}:cpu-group:{model_id}"
        signature = self.store.state(group_key)
        groups = None
        if signature is None:
            groups = self._groups(units)
            if not groups:
                raise GenerationError("Chưa có máy CPU sẵn sàng cho model này. Kiểm tra tab Máy CPU rồi bấm Tiếp tục.")
            signature = max(groups, key=lambda key: len(groups[key]))
            self.store.set_state(group_key, signature)
        revision = signature[0]
        self.store.set_state(f"{self.job_id}:model:{model_id}", revision)
        pending = deque()
        for unit in units:
            request = unit.request.model_copy(update={"execution_backend": "cpu", "model_revision": revision})
            unit = replace(unit, request=request)
            digest, cache, proof = context.cache_paths(request, unit.destination, is_pc=True)
            if not context.copy_verified(cache, proof, unit.destination):
                pending.append((unit, digest))
        if not pending:
            return

        groups = groups if groups is not None else self._groups([unit for unit, _digest in pending])
        available = deque(groups.get(tuple(signature), ()))
        self._distribute(context, pending, available, cancel_event, total=len(units), rate=signature[1])

    def _run_unit(self, context, profile, unit, digest, rate):
        slot = ExistingWorkerLifecycle(self.store, self.job_id, profile, unit=digest, allowed=self._allowed, sample_rate=rate)
        execution = ManagedExecution(self.store, self.job_id, slot, verified_lock=context.verified_lock)
        execution.execute(unit.request, unit.destination, cancel_event=unit.cancel_event,
                          reference_audio=unit.reference_audio)

    def _distribute(self, context, pending, available, cancel_event, *, total, rate):
        active = {}
        failure = None
        with ThreadPoolExecutor(max_workers=self.limit) as executor:
            while pending or active:
                if failure is None:
                    try:
                        context.check(cancel_event)
                    except GenerationCancelled as error:
                        failure = error
                paused = self.store.get(self.job_id)["paused"]
                while not (failure or paused) and pending and available and len(active) < self.limit:
                    profile = available.popleft()
                    if not self._allowed(profile):
                        continue
                    unit, digest = pending.popleft()
                    future = executor.submit(self._run_unit, context, profile, unit, digest, rate)
                    active[future] = profile, unit, digest
                if not active:
                    if failure is not None:
                        raise failure
                    if paused:
                        context.status("Đã tạm dừng cấp đoạn mới cho nhóm CPU")
                        time.sleep(0.5)
                        continue
                    raise GenerationError("Nhóm CPU chưa có máy cùng phiên bản model để nhận đoạn còn lại. Bấm Tiếp tục khi máy sẵn sàng.")

                context.status(f"Nhóm CPU · {total - len(pending) - len(active)}/{total} đoạn đã xác minh · {len(active)} máy")
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    profile, unit, digest = active.pop(future)
                    try:
                        future.result()
                    except PcWorkerUnavailable:
                        pending.appendleft((unit, digest))
                    except (GenerationError, OSError, ValueError) as error:
                        failure = failure or error
                    else:
                        available.appendleft(profile)
            if failure is not None:
                raise failure
