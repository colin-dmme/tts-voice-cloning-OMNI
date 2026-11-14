"""Shared CPU queue and host controls on the Studio MCP server."""
from __future__ import annotations

from typing import Any, Literal

from .client import ColabClient, public_job
from .cpu_report import cpu_contributions
from .pc_lifecycle import broker_for as _client
from .targets import profile_store, resolve_pc_profile
from .local_cpu import LOCAL_CPU_ID, LOCAL_CPU_LABEL


def admin_profile():
    profiles = profile_store().load().profiles
    return next((profile for profile in profiles if profile.enabled and profile.broker_url ==
                 "https://tts-compute.tainguyenso.online"), None) or next(
        (profile for profile in profiles if profile.enabled), None
    )


def register_tools(mcp):
    @mcp.tool()
    def cpu_worker_status(worker_profile_id: str | None = None) -> dict[str, Any]:
        """Đọc máy CPU, model đã cài và job đang theo dõi. Dùng profile ID khi có nhiều broker."""
        profile = resolve_pc_profile(worker_profile_id) if worker_profile_id else admin_profile()
        local = ColabClient()
        jobs = [public_job(row) | {"verified_units": local.store.state(row["job_id"] + ":verified_units", 0),
                                   "cpu_contributions": cpu_contributions(local.store, row["job_id"], row["payload"]["remote_target"])}
                for row in local.store.list(50) if row["job_id"].startswith("cpu-job-")]
        local_cpu = {"worker_profile_id": LOCAL_CPU_ID, "display_name": LOCAL_CPU_LABEL,
                     "pool_enabled": profile_store().load().cpu_pool_local}
        if profile is None:
            return {"state": "needs_broker", "devices": [], "jobs": jobs, "local_cpu": local_cpu}
        broker = _client(profile)
        document = profile_store().load()
        enrolled = {item.worker_id: item for item in document.profiles
                    if item.is_pc and item.broker_url == profile.broker_url and item.enabled}
        devices = broker.list_pc_devices()
        registered = {item.capabilities.worker_id: item.capabilities for item in broker.list_workers()}
        for device in devices:
            worker = registered.get(device["worker_id"])
            device["models"] = [model.model_dump(mode="json") for model in worker.models] if worker else []
            saved = enrolled.get(device["worker_id"])
            device["worker_profile_id"] = saved.profile_id if saved else device["worker_id"]
            device["pool_enabled"] = bool(saved and saved.pool_enabled and not device.get("revoked"))
        return {"state": "ok", "devices": devices, "jobs": jobs, "cpu_pool_limit": document.cpu_pool_limit,
                "local_cpu": local_cpu}

    @mcp.tool()
    def cpu_worker_control(worker_profile_id: str, action: Literal["pause", "resume", "stop", "include_pool", "exclude_pool"]) -> dict[str, Any]:
        """Điều khiển máy đã ghép hoặc chọn máy tham gia nhóm chia tải."""
        if worker_profile_id == LOCAL_CPU_ID:
            if action not in {"include_pool", "exclude_pool"}:
                raise ValueError("CPU máy này dùng include_pool hoặc exclude_pool để bật/tắt cấp đoạn mới.")
            profile_store().set_cpu_pool_local(action == "include_pool")
            return {"worker_profile_id": LOCAL_CPU_ID, "pool_enabled": action == "include_pool"}
        profile = resolve_pc_profile(worker_profile_id)
        if action in {"include_pool", "exclude_pool"}:
            enabled = action == "include_pool"
            profile_store().set_cpu_pool_worker(profile.profile_id, enabled)
            return {"worker_profile_id": profile.profile_id, "pool_enabled": enabled}
        return _client(profile).control_pc_device(profile.worker_id, action)

    @mcp.tool()
    def cpu_job_control(job_id: str, action: Literal["pause", "resume", "cancel"]) -> dict[str, Any]:
        """Tạm dừng, tiếp tục hoặc hủy một job CPU. Các đoạn đã kiểm được giữ để tiếp tục."""
        if not job_id.startswith("cpu-job-"):
            raise ValueError("Cần mã job CPU.")
        return ColabClient().control(job_id, action)
