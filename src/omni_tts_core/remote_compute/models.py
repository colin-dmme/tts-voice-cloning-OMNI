from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PROTOCOL_VERSION = "1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RemoteJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_REMOTE_JOB_STATUSES = {
    RemoteJobStatus.SUCCEEDED,
    RemoteJobStatus.FAILED,
    RemoteJobStatus.CANCELLED,
}


class WorkerRuntimeInfo(BaseModel):
    platform: str = "unknown"
    cpu: str = ""
    ram_mb: int | None = Field(default=None, ge=0)
    gpu: str | None = None
    vram_mb: int | None = Field(default=None, ge=0)


class WorkerModelCapability(BaseModel):
    model_id: str
    provider_id: str
    execution_backend: Literal["cpu", "cuda", "remote"]
    sample_rate: int = Field(ge=8000, le=384000)
    output_formats: tuple[str, ...] = ("wav",)
    supports_streaming: bool = False
    supports_profile_clone: bool = False

    @field_validator("model_id", "provider_id")
    @classmethod
    def require_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model_id và provider_id không được để trống")
        return normalized


class WorkerCapabilities(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    worker_id: str
    display_name: str
    worker_type: str = "generic"
    runtime: WorkerRuntimeInfo = Field(default_factory=WorkerRuntimeInfo)
    models: tuple[WorkerModelCapability, ...]
    max_concurrency: int = Field(default=1, ge=1, le=64)
    registered_at: str = Field(default_factory=utc_now)

    @field_validator("worker_id", "display_name", "worker_type")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Định danh worker không được để trống")
        return normalized

    @model_validator(mode="after")
    def require_supported_model(self):
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"Protocol worker {self.protocol_version} không tương thích với {PROTOCOL_VERSION}"
            )
        if not self.models:
            raise ValueError("Worker phải công bố ít nhất một model")
        model_ids = [item.model_id for item in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("Worker không được công bố model_id trùng nhau")
        return self


class WorkerRecord(BaseModel):
    capabilities: WorkerCapabilities
    last_seen_at: str


class RemoteTtsRequest(BaseModel):
    protocol_version: str = PROTOCOL_VERSION
    client_job_id: str
    inference_unit_id: str
    idempotency_key: str
    model_id: str
    text: str
    language: str = "vi"
    speaker_id: str | None = None
    provider_options: dict[str, Any] = Field(default_factory=dict)
    output_format: Literal["wav"] = "wav"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "client_job_id", "inference_unit_id", "idempotency_key", "model_id", "text"
    )
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Trường bắt buộc không được để trống")
        return normalized

    @model_validator(mode="after")
    def validate_protocol(self):
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(
                f"Protocol job {self.protocol_version} không tương thích với {PROTOCOL_VERSION}"
            )
        return self


class RemoteTtsResultMetadata(BaseModel):
    audio_format: Literal["wav"] = "wav"
    sample_rate: int = Field(ge=8000, le=384000)
    channels: int = Field(default=1, ge=1, le=8)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    byte_size: int = Field(default=0, ge=0)
    sha256: str
    timing: dict[str, float] = Field(default_factory=dict)
    model_runtime: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("sha256 phải có đúng 64 ký tự hex")
        return normalized


class RemoteTtsJob(BaseModel):
    job_id: str
    request: RemoteTtsRequest
    status: RemoteJobStatus = RemoteJobStatus.QUEUED
    worker_id: str = ""
    attempt_id: str = ""
    attempt_count: int = Field(default=0, ge=0)
    lease_expires_at: str = ""
    cancel_requested: bool = False
    result: RemoteTtsResultMetadata | None = None
    error: str = ""
    retryable: bool = False
    failure_kind: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class JobLease(BaseModel):
    job: RemoteTtsJob | None = None
    lease_token: str = ""
    lease_expires_at: str = ""


class BrokerConnectionOptions(BaseModel):
    base_url: str
    auth_env: str = "COLIN_COMPUTE_BROKER_TOKEN"
    auth_token_file: Path | None = None
    connect_timeout_seconds: float = Field(default=10.0, ge=1.0, le=120.0)
    request_timeout_seconds: float = Field(default=120.0, ge=10.0, le=7200.0)
    max_retries: int = Field(default=1, ge=0, le=5)

    @model_validator(mode="after")
    def normalize(self):
        self.base_url = self.base_url.strip().rstrip("/")
        self.auth_env = self.auth_env.strip() or "COLIN_COMPUTE_BROKER_TOKEN"
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Broker URL phải bắt đầu bằng http:// hoặc https://")
        return self


class WorkerProfile(BaseModel):
    profile_id: str
    label: str
    broker_url: str
    worker_id: str
    auth_env: str = "COLIN_COMPUTE_BROKER_TOKEN"
    auth_token_file: Path | None = None
    enabled: bool = True

    @field_validator("profile_id", "label", "worker_id")
    @classmethod
    def require_profile_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Profile worker không được để trống định danh")
        return normalized

    @model_validator(mode="after")
    def normalize_connection(self):
        self.broker_url = self.broker_url.strip().rstrip("/")
        self.auth_env = self.auth_env.strip() or "COLIN_COMPUTE_BROKER_TOKEN"
        if not self.broker_url.startswith(("http://", "https://")):
            raise ValueError("Broker URL phải bắt đầu bằng http:// hoặc https://")
        return self


class WorkerSelectionSettings(BaseModel):
    selected_profile_id: str = ""
    switch_policy: Literal[
        "selected_only", "ask_before_switch", "automatic_failover"
    ] = "selected_only"

    @field_validator("selected_profile_id")
    @classmethod
    def normalize_selection(cls, value: str) -> str:
        return value.strip()
