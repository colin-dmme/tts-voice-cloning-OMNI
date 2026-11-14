"""Send an installed manual Piper package to the checked CPU workers."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from omni_tts_core.model_registry import ModelRegistry
from omni_tts_shared.errors import ConfigError, GenerationError

from .local_cpu import _file_digest
from .pc_lifecycle import ExistingWorkerLifecycle, supports_unit

SYNC_STAGES = {
    "queued": "Chờ đồng bộ", "downloading": "Đang tải model", "checking": "Đang kiểm tra WAV",
    "ready": "Model sẵn sàng", "error": "Lỗi đồng bộ, worker sẽ thử lại",
}


@dataclass(frozen=True)
class InstalledPiperPackage:
    manifest: dict
    files: dict

    @property
    def signature(self):
        hashes = [self.manifest[role]["sha256"] for role in ("onnx", "config")]
        revision = "files-sha256:" + hashlib.sha256(json.dumps(hashes).encode("ascii")).hexdigest()
        return revision, self.manifest["sample_rate"]

    @classmethod
    def find(cls, model_id):
        if not re.fullmatch(r"piper_[a-z0-9_]{1,96}", model_id):
            return None
        try:
            spec = ModelRegistry().get(model_id)
        except ConfigError:
            return None
        if spec.provider != "piper" or spec.source_kind != "manual":
            return None
        runtime = spec.runtime
        files = {role: spec.local_path / runtime[key] for role, key in
                 (("onnx", "model_file"), ("config", "config_file"))}
        if set(runtime.get("required_files", [])) - {runtime["model_file"], runtime["config_file"]}:
            raise GenerationError("Tự đồng bộ Piper cần package gồm ONNX và JSON.")
        if not all(path.is_file() for path in files.values()):
            raise GenerationError("Máy này thiếu tệp ONNX hoặc JSON của model Piper để đồng bộ.")
        descriptors = {}
        for role, path in files.items():
            size = path.stat().st_size
            if not 0 < size <= (96 if role == "onnx" else 2) * 1024 * 1024:
                raise GenerationError("Tệp Piper vượt giới hạn kích thước đồng bộ.")
            digest = _file_digest(path)
            expected = runtime.get("model_sha256" if role == "onnx" else "config_sha256")
            if expected and digest != expected.lower():
                raise GenerationError("Tệp Piper trên máy này không khớp SHA-256 đã khai báo.")
            descriptors[role] = {"sha256": digest, "size": size}
        try:
            rate = int(json.loads(files["config"].read_bytes())["audio"]["sample_rate"])
        except (ValueError, KeyError, TypeError) as error:
            raise GenerationError("JSON Piper thiếu tần số lấy mẫu hợp lệ.") from error
        return cls({"model_id": model_id, "label": spec.display_name, "sample_rate": rate, **descriptors}, files)


class PiperPoolSync:
    def __init__(self, lifecycle, package, units):
        self.pool, self.package, self.units = lifecycle, package, units
        self.stages = {}

    def _notice(self, profile, stage):
        if stage != self.stages.get(profile.worker_id):
            self.stages[profile.worker_id] = stage
            level = ("success" if stage == SYNC_STAGES["ready"] else "warning"
                     if stage in {SYNC_STAGES["error"], "Broker chưa hỗ trợ đồng bộ Piper"} else "sync")
            self.pool.store.add_event(self.pool.job_id, f"{profile.label} · {stage} · {self.package.manifest['label']}.", level)

    def refresh(self, check):
        broker = self.pool.broker
        revision, rate = self.package.signature
        manifest = self.package.manifest
        profiles = [profile for profile in self.pool.profiles if self.pool._allowed(profile)]
        if not profiles:
            return [], False
        devices = {device["worker_id"]: device for device in broker.list_pc_devices()
                   if not device.get("revoked")}
        records = {row.capabilities.worker_id: row.capabilities for row in broker.list_workers()
                   if row.capabilities.worker_type == "remote_pc"}
        ready, missing = [], []
        can_wait = False
        for profile in profiles:
            device = devices.get(profile.worker_id)
            if device is None:
                self._notice(profile, "Chưa có quyền kết nối")
                continue
            worker = records.get(profile.worker_id)
            matching = worker and any((model.revision, model.sample_rate) == (revision, rate)
                                       and all(supports_unit(model, unit.request) for unit in self.units)
                                       for model in worker.models)
            assignment = next((item for item in device.get("model_sync", [])
                               if item["model_id"] == manifest["model_id"] and item["revision"] == revision), None)
            online = ExistingWorkerLifecycle._recent(device.get("last_seen_at"))
            running = device.get("desired_state") == "running" and device.get("observed_state") not in {"paused", "stopped"}
            if not matching and assignment is None:
                missing.append(profile)
            if not online:
                self._notice(profile, "Offline · chờ máy kết nối")
            elif not running:
                self._notice(profile, "Đang ngừng nhận việc")
            elif matching and device.get("observed_state") in {"idle", "busy"}:
                self._notice(profile, "Model sẵn sàng")
                ready.append(profile)
            else:
                can_wait = True
                version = device.get("worker_version")
                stage = assignment["stage"] if assignment else "queued"
                if stage == "ready":
                    stage = "checking"
                note = (SYNC_STAGES.get(stage, SYNC_STAGES["queued"]) if version
                        else "Chờ CPU Worker tự cập nhật")
                self._notice(profile, note)
        if missing:
            if broker.health().get("pc_model_sync") != "1":
                for profile in missing:
                    self._notice(profile, "Broker chưa hỗ trợ đồng bộ Piper")
                return ready, False
            check()
            broker.ensure_piper_package(manifest, self.package.files, check)
            check()
            worker_ids = [profile.worker_id for profile in missing if self.pool._allowed(profile)]
            if worker_ids:
                assigned = broker.assign_piper_model(manifest, worker_ids)
                for profile in missing:
                    if profile.worker_id in assigned:
                        self._notice(profile, "Đã xếp đồng bộ")
        return ready, can_wait
