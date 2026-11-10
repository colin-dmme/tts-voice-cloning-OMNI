from __future__ import annotations

from urllib.parse import urlsplit

from omni_tts_core.paths import PROJECT_ROOT
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import PC_EXECUTION_KINDS


def pc_target(settings) -> bool:
    return settings.runtime_target == "remote" and getattr(settings, "remote_execution_kind", "") in PC_EXECUTION_KINDS


def profile_store():
    from .broker.profiles import WorkerProfileStore
    return WorkerProfileStore(PROJECT_ROOT / "config" / "remote_compute_workers.json")


def resolve_pc_profile(profile_id: str):
    document = profile_store().load()
    profile = next((item for item in document.profiles
                    if item.profile_id == profile_id and item.enabled and item.is_pc), None)
    if profile is None:
        raise ConfigError("Chọn một máy CPU đã ghép và đang bật trong mục Máy chạy.")
    return _validate_pc_profile(profile)


def resolve_pc_pool():
    document = profile_store().load()
    profiles = list({item.worker_id: _validate_pc_profile(item) for item in document.profiles
                     if item.enabled and item.is_pc and item.pool_enabled}.values())
    if not profiles:
        raise ConfigError("Bật ít nhất một máy trong tab Máy CPU để chia tải.")
    if len({item.broker_url for item in profiles}) != 1:
        raise ConfigError("Các máy tham gia chia tải cần dùng chung một broker.")
    return profiles, document.cpu_pool_limit


def _validate_pc_profile(profile):
    address = urlsplit(profile.broker_url)
    if (not address.hostname or address.username or address.password or address.query or address.fragment
            or address.scheme != "https" and address.hostname not in ("127.0.0.1", "::1", "localhost")):
        raise ConfigError("Máy CPU cần kết nối broker HTTPS hoặc loopback.")
    return profile
