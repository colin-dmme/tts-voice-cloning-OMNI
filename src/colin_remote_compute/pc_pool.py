"""Distribute one Studio job over enrolled CPU machines on the same broker."""
from __future__ import annotations

import time
import json
import hashlib
from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from types import SimpleNamespace

from omni_tts_shared.errors import GenerationCancelled, GenerationError

from .broker.profiles import WorkerProfileDocument
from .context import ManagedExecution
from .pc_lifecycle import (
    ExistingWorkerLifecycle, PcWorkerUnavailable,
    broker_for, cancel_pending_unit, supports_unit,
)
from .targets import profile_store
from .local_cpu import LOCAL_CPU_ID, LOCAL_CPU_LABEL, LocalCpuExecutor
from .piper_model_sync import InstalledPiperPackage, PiperPoolSync


MODEL_SYNC_WAIT_SECONDS = 180


class CpuPoolLifecycle:
    is_existing_worker = True
    is_cpu_pool = True

    def __init__(self, store, job_id, profiles, limit, *, include_local=False):
        self.store, self.job_id, self.profiles, self.limit = store, job_id, profiles, limit
        self.document = WorkerProfileDocument(profiles=profiles, cpu_pool_limit=limit)
        self.broker = broker_for(profiles[0]) if profiles else None
        self.include_local, self.local = include_local, None
        self.local_profile = SimpleNamespace(profile_id=LOCAL_CPU_ID, worker_id=LOCAL_CPU_ID, label=LOCAL_CPU_LABEL)

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
        if profile.profile_id == LOCAL_CPU_ID:
            return self.include_local and profile_store().load().cpu_pool_local
        return any(current.profile_id == profile.profile_id and current.worker_id == profile.worker_id
                   and current.broker_url == profile.broker_url and current.enabled and current.pool_enabled
                   for current in profile_store().load().profiles)

    def _local_groups(self, units):
        groups = defaultdict(list)
        if self.include_local and self._allowed(self.local_profile):
            try:
                if self.local is None:
                    self.local = LocalCpuExecutor(units[0].request.model_id)
                model = self.local.capability
                if all(supports_unit(model, unit.request) for unit in units):
                    groups[(model.revision, model.sample_rate)].append(self.local_profile)
            except (GenerationError, OSError, ValueError) as error:
                self.store.add_event(self.job_id, f"Bỏ qua {LOCAL_CPU_LABEL} · {error}", "warning")
        return groups

    def _groups(self, units):
        groups = self._local_groups(units)
        if self.broker is None:
            return groups
        try:
            return self._remote_groups(units, groups)
        except GenerationError:
            if not groups:
                raise
            self.store.add_event(self.job_id, "Chưa liên lạc được broker · tiếp tục bằng CPU máy này; giữ các đoạn từ xa chưa đối soát.", "warning")
            return groups

    def _remote_groups(self, units, groups):
        devices = {row["worker_id"]: row for row in self.broker.list_pc_devices()
                   if not row.get("revoked") and row.get("desired_state") == "running"
                   and row.get("observed_state") in {"idle", "busy"}
                   and ExistingWorkerLifecycle._recent(row.get("last_seen_at"))}
        workers = {row.capabilities.worker_id: row.capabilities for row in self.broker.list_workers()
                   if row.capabilities.worker_type == "remote_pc"}
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
        try:
            self._dispatch(context, units)
        finally:
            manifest = context.units / "segments.json"
            if manifest.is_file():
                rows = json.loads(manifest.read_text(encoding="utf-8"))
                for row in rows:
                    cache = context.units / row["file"]
                    proof = cache.with_suffix(cache.suffix + ".sha256")
                    row["verified"] = bool(cache.is_file() and proof.is_file()
                                           and hashlib.sha256(cache.read_bytes()).hexdigest() == proof.read_text().strip())
                manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            if self.local is not None:
                self.local.close()

    def _dispatch(self, context, units):
        if not units:
            return
        cancel_event = units[0].cancel_event
        context.check(cancel_event)
        model_id = units[0].request.model_id
        group_key = f"{self.job_id}:cpu-group:{model_id}"
        signature = self.store.state(group_key)
        package = None
        if self.broker is not None and any(self._allowed(profile) for profile in self.profiles):
            try:
                package = InstalledPiperPackage.find(model_id)
            except (GenerationError, OSError, ValueError) as error:
                self.store.add_event(self.job_id, f"Chưa thể gửi model Piper từ máy này · {error}", "warning")
        if package is not None and signature is not None and tuple(signature) != package.signature:
            self.store.add_event(self.job_id, "Lượt này dùng phiên bản Piper đã lưu. Cần đúng phiên bản đó để chia tải.", "warning")
            package = None
        sync = PiperPoolSync(self, package, units) if package is not None else None
        groups = None
        if signature is None:
            if sync:
                signature = package.signature
            else:
                groups = self._groups(units)
                if not groups:
                    raise GenerationError("Chưa có máy CPU sẵn sàng cho model này. Kiểm tra tab Máy CPU rồi bấm Tiếp tục.")
                signature = max(groups, key=lambda key: len(groups[key]))
            self.store.set_state(group_key, signature)
        revision = signature[0]
        self.store.set_state(f"{self.job_id}:model:{model_id}", revision)
        pending = deque()
        manifest = []
        for unit in units:
            request = unit.request.model_copy(update={"execution_backend": "cpu", "model_revision": revision})
            unit = replace(unit, request=request)
            digest, cache, proof = context.cache_paths(request, unit.destination, is_pc=True)
            manifest.append({"unit": request.inference_unit_id, "file": cache.name})
            if context.copy_verified(cache, proof, unit.destination):
                self.store.record_cpu_result(self.job_id, digest, "", len(request.batch_texts) or 1)
            else:
                pending.append((unit, digest))
        (context.units / "segments.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if not pending:
            return

        if groups is None:
            groups = self._local_groups(units) if sync else self._groups(units)
        available = deque(groups.get(tuple(signature), ()))
        selected = ", ".join(profile.label for profile in available)
        if selected:
            self.store.add_event(self.job_id, f"Nhóm CPU · sẵn sàng {selected} · tối đa {self.limit} máy cùng lúc.", "info")
        elif sync:
            self.store.add_event(self.job_id, "Nhóm CPU · đang kiểm tra model trên các máy đã chọn.", "sync")
        if self.local is not None and self.local_profile not in available:
            self.store.add_event(self.job_id, "CPU máy này không cùng phiên bản model/tần số với nhóm đang dùng; tiếp tục bằng các máy tương thích.", "warning")
        self._distribute(context, pending, available, cancel_event, total=len(units), rate=signature[1], sync=sync)

    def _run_unit(self, context, profile, unit, digest, rate):
        if profile.profile_id == LOCAL_CPU_ID:
            pending_key = f"{self.job_id}:pc-pending:{digest}"
            if self.store.state(pending_key):
                if self.broker is None:
                    raise GenerationError("Cần đối soát đoạn đã gửi trước khi chuyển về CPU máy này.")
                cancel_pending_unit(self.store, self.broker, pending_key)
            try:
                return self.local.execute(context, unit, digest, rate)
            except (GenerationError, OSError, ValueError) as error:
                self.local.close()
                raise PcWorkerUnavailable("CPU máy này chưa hoàn tất đoạn; thử lại trên máy phù hợp.") from error
        slot = ExistingWorkerLifecycle(self.store, self.job_id, profile, unit=digest, allowed=self._allowed, sample_rate=rate)
        execution = ManagedExecution(self.store, self.job_id, slot, verified_lock=context.verified_lock)
        return execution.execute(unit.request, unit.destination, cancel_event=unit.cancel_event,
                                 reference_audio=unit.reference_audio)

    def _distribute(self, context, pending, available, cancel_event, *, total, rate, sync=None):
        active = {}
        completed = total - len(pending)
        retries = defaultdict(int)
        cooldowns = {}
        failure = None
        sync_future, next_refresh, wait_until = None, 0.0, 0.0
        remote_profiles = {profile.profile_id for profile in self.profiles}
        ready_ids = set()
        with ThreadPoolExecutor(max_workers=1) as sync_executor, ThreadPoolExecutor(max_workers=self.limit) as executor:
            while pending or active:
                if failure is None:
                    try:
                        context.check(cancel_event)
                    except GenerationCancelled as error:
                        failure = error
                paused = self.store.get(self.job_id)["paused"]
                tick = time.monotonic()
                if sync_future and sync_future.done():
                    try:
                        ready, waiting = sync_future.result()
                    except (GenerationError, OSError, ValueError):
                        self.store.add_event(self.job_id, "Đồng bộ Piper gián đoạn · sẽ thử kết nối lại.", "warning")
                        ready, waiting = [], True
                    ready_ids = {profile.profile_id for profile in ready}
                    available = deque(profile for profile in available
                                      if profile.profile_id not in remote_profiles or profile.profile_id in ready_ids)
                    occupied = {profile.profile_id for profile, _, _ in active.values()}
                    occupied.update(profile.profile_id for profile in available)
                    occupied.update(cooldowns)
                    available.extend(profile for profile in ready if profile.profile_id not in occupied
                                     and retries[profile.profile_id] < 3)
                    if waiting and not wait_until:
                        wait_until = tick + MODEL_SYNC_WAIT_SECONDS
                    elif not waiting:
                        wait_until = 0
                    sync_future, next_refresh = None, tick + 4
                if (sync and sync_future is None and pending and not (failure or paused) and tick >= next_refresh
                        and (active or available or not wait_until or tick < wait_until)):
                    sync_future = sync_executor.submit(sync.refresh, lambda: context.check(cancel_event))
                for profile_id, (deadline, profile) in list(cooldowns.items()):
                    if tick >= deadline:
                        if not sync or profile_id not in remote_profiles or profile_id in ready_ids:
                            available.append(profile)
                        del cooldowns[profile_id]
                while not (failure or paused) and pending and available and len(active) < self.limit:
                    profile = available.popleft()
                    if not self._allowed(profile):
                        continue
                    unit, digest = pending.popleft()
                    self.store.add_event(self.job_id, f"{profile.label} · cấp đoạn {unit.request.inference_unit_id}.", "dispatch")
                    future = executor.submit(self._run_unit, context, profile, unit, digest, rate)
                    active[future] = profile, unit, digest
                if not active:
                    if failure is not None:
                        raise failure
                    if paused:
                        context.status("Đã tạm dừng cấp đoạn mới cho nhóm CPU")
                        time.sleep(0.5)
                        continue
                    if cooldowns:
                        context.status("Đang chờ máy CPU kết nối lại")
                        time.sleep(0.5)
                        continue
                    if sync_future is not None or tick < wait_until:
                        context.status(f"Nhóm CPU · {completed}/{total} đoạn đã xác minh · chờ đồng bộ Piper", log_message=False)
                        time.sleep(0.5)
                        continue
                    raise GenerationError("Nhóm CPU chưa có máy cùng phiên bản model để nhận đoạn còn lại. Bấm Tiếp tục khi máy sẵn sàng.")

                machines = ", ".join(profile.label for profile, _, _ in active.values())
                message = f"Nhóm CPU · {completed}/{total} đoạn đã xác minh · {machines}"
                if self.store.get(self.job_id)["kind"] == "text":
                    self.store.update(self.job_id, progress=round(completed / total * 95, 2))
                context.status(message, log_message=False)
                done, _ = wait(active, timeout=1, return_when=FIRST_COMPLETED)
                for future in done:
                    profile, unit, digest = active.pop(future)
                    try:
                        used_worker = future.result()
                    except PcWorkerUnavailable:
                        self.store.add_event(self.job_id, f"{profile.label} · đoạn {unit.request.inference_unit_id} chưa hoàn tất, sẽ thử lại.", "warning")
                        pending.appendleft((unit, digest))
                        retries[profile.profile_id] += 1
                        if retries[profile.profile_id] < 3:
                            cooldowns[profile.profile_id] = (time.monotonic() + 10 * retries[profile.profile_id], profile)
                    except (GenerationError, OSError, ValueError) as error:
                        self.store.add_event(self.job_id, f"{profile.label} · lỗi ở đoạn {unit.request.inference_unit_id}. Đã giữ các đoạn xác minh.", "error")
                        failure = failure or error
                    else:
                        completed += 1
                        label = next((item.label for item in [self.local_profile, *self.profiles]
                                      if item.worker_id == used_worker), used_worker or profile.label)
                        self.store.add_event(self.job_id, f"{label} · hoàn tất đoạn {unit.request.inference_unit_id} · {completed}/{total} đoạn đã xác minh.", "success")
                        retries[profile.profile_id] = 0
                        if not sync or profile.profile_id not in remote_profiles or profile.profile_id in ready_ids:
                            available.appendleft(profile)
            if failure is not None:
                raise failure
