from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from pathlib import Path
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from omni_tts_shared.errors import ConfigError, GenerationError

from .models import (
    TERMINAL_REMOTE_JOB_STATUSES,
    BrokerConnectionOptions,
    RemoteTtsJob,
    RemoteTtsRequest,
    WorkerRecord,
)


class BrokerClient:
    """HTTP client for the versioned Colin Compute broker protocol."""

    def __init__(self, options: BrokerConnectionOptions) -> None:
        self.options = options

    def health(self) -> dict[str, Any]:
        payload = self._json_request("GET", "/health", authenticated=False)
        if not isinstance(payload, dict):
            raise GenerationError("Broker trả về health payload không hợp lệ.")
        return payload

    def list_workers(self) -> list[WorkerRecord]:
        payload = self._json_request("GET", "/v1/workers")
        if not isinstance(payload, list):
            raise GenerationError("Broker trả về danh sách worker không hợp lệ.")
        return [WorkerRecord.model_validate(item) for item in payload]

    def submit(self, request: RemoteTtsRequest, *, worker_id: str = "") -> RemoteTtsJob:
        payload = request.model_dump(mode="json")
        if worker_id.strip():
            payload["requested_worker_id"] = worker_id.strip()
        return RemoteTtsJob.model_validate(
            self._json_request("POST", "/v1/jobs", payload=payload)
        )

    def get_job(self, job_id: str) -> RemoteTtsJob:
        return RemoteTtsJob.model_validate(
            self._json_request("GET", f"/v1/jobs/{quote(job_id, safe='')}")
        )

    def cancel(self, job_id: str) -> RemoteTtsJob:
        return RemoteTtsJob.model_validate(
            self._json_request("POST", f"/v1/jobs/{quote(job_id, safe='')}/cancel")
        )

    def wait_for_terminal(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float | None = None,
        cancel_event: Event | None = None,
    ) -> RemoteTtsJob:
        started = time.monotonic()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return self.cancel(job_id)
            job = self.get_job(job_id)
            if job.status in TERMINAL_REMOTE_JOB_STATUSES:
                return job
            if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
                raise GenerationError(f"Hết thời gian chờ remote job {job_id}.")
            time.sleep(max(0.1, poll_interval_seconds))

    def download_result(self, job: RemoteTtsJob, destination: Path) -> Path:
        if job.result is None:
            raise GenerationError(f"Remote job {job.job_id} chưa có metadata kết quả.")
        body = self._request("GET", f"/v1/jobs/{quote(job.job_id, safe='')}/result")
        digest = hashlib.sha256(body).hexdigest()
        if digest != job.result.sha256:
            raise GenerationError(
                f"Audio remote job {job.job_id} sai SHA-256, không ghi đè tệp đầu ra."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(body)
        os.replace(temporary, destination)
        return destination

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> object:
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        raw = self._request(
            method,
            path,
            body=body,
            extra_headers=headers,
            authenticated=authenticated,
        )
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationError(f"Broker trả về JSON không hợp lệ tại {path}.") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> bytes:
        headers = {"Accept": "application/json, audio/wav"}
        if authenticated:
            headers.update(self._auth_headers())
        headers.update(extra_headers or {})
        attempts = self.options.max_retries + 1
        retryable = {502, 503, 504, 520, 521, 522, 523, 524}
        url = f"{self.options.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=self.options.request_timeout_seconds) as response:
                    return response.read()
            except HTTPError as exc:
                detail = _http_error_detail(exc)
                last_error = GenerationError(
                    f"Broker trả lỗi HTTP {exc.code}: {detail or exc.reason}"
                )
                if exc.code not in retryable or attempt + 1 >= attempts:
                    raise last_error from exc
            except (URLError, socket.timeout, TimeoutError) as exc:
                last_error = GenerationError(f"Không kết nối được broker {url}: {exc}")
                if attempt + 1 >= attempts:
                    raise last_error from exc
        raise last_error or GenerationError(f"Không kết nối được broker {url}.")

    def _auth_headers(self) -> dict[str, str]:
        token = os.environ.get(self.options.auth_env, "").strip()
        if not token:
            raise ConfigError(f"Thiếu token trong biến môi trường {self.options.auth_env}.")
        return {"Authorization": f"Bearer {token}"}


def _http_error_detail(error: HTTPError) -> str:
    try:
        body = error.read(4096).decode("utf-8", errors="replace")
        payload = json.loads(body)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if isinstance(payload, dict):
        return str(payload.get("detail") or payload.get("error") or payload)[:500]
    return str(payload)[:500]
