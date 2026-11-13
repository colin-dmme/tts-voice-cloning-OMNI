from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import json
import os
import socket
import time
from pathlib import Path
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from omni_tts_shared.errors import ConfigError, GenerationError

from .models import (
    TERMINAL_REMOTE_JOB_STATUSES,
    BrokerConnectionOptions,
    RemoteTtsJob,
    RemoteTtsRequest,
    WorkerRecord,
    PairingPreview,
)


class BrokerConnectionError(GenerationError):
    code = "broker_unavailable"
    retryable = True


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Broker redirect denied", headers, fp)


class BrokerClient:
    """HTTP client for the versioned Colin Compute broker protocol."""

    def __init__(self, options: BrokerConnectionOptions, *, no_redirect: bool = False) -> None:
        self.options = options
        self._opener = build_opener(_NoRedirect()) if no_redirect else None
        self._reference_assets: set[str] = set()

    def ensure_reference_audio(self, audio: bytes) -> str:
        if len(audio) > 10 * 1024 * 1024:
            raise GenerationError("Audio mẫu vượt giới hạn 10 MiB.")
        asset_id = hashlib.sha256(audio).hexdigest()
        if asset_id not in self._reference_assets:
            path = f"/v1/assets/{asset_id}"
            status = self._json_request("GET", path + "/status")
            if not isinstance(status, dict) or not status.get("exists"):
                self._request("PUT", path, body=audio, extra_headers={"Content-Type": "audio/wav"})
            self._reference_assets.add(asset_id)
        return asset_id

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

    def inspect_pairing(self, user_code: str) -> PairingPreview:
        return PairingPreview.model_validate(self._json_request(
            "POST", "/v1/pairing/inspect", payload={"user_code": user_code.strip().upper()},
        ))

    def get_pairing_launch(self, launch_id: str) -> dict[str, Any]:
        result = self._json_request("GET", f"/v1/pairing/launch/{quote(launch_id, safe='')}")
        if not isinstance(result, dict):
            raise GenerationError("Broker chưa xác nhận phiên khởi động Colab.")
        return result

    def approve_pairing(self, user_code: str, preview: PairingPreview) -> dict[str, Any]:
        payload = {key: getattr(preview, key) for key in ("pairing_id", "worker_id", "provider", "device")}
        if preview.launch_id:
            payload["launch_id"] = preview.launch_id
        payload["user_code"] = user_code.strip().upper()
        # An uncertain approval must never be submitted again automatically.
        client = BrokerClient(self.options.model_copy(update={"max_retries": 0}))
        result = client._json_request("POST", "/v1/pairing/approve", payload=payload)
        if not isinstance(result, dict) or result.get("status") != "approved":
            raise GenerationError("Broker chưa xác nhận ghép nối. Không tự gửi lại yêu cầu.")
        return result

    def revoke_pairing(self, worker_id: str) -> dict[str, Any]:
        client = BrokerClient(self.options.model_copy(update={"max_retries": 0}))
        result = client._json_request("POST", f"/v1/workers/{quote(worker_id, safe='')}/revoke-pairing")
        if not isinstance(result, dict) or result.get("status") != "revoked":
            raise GenerationError("Broker chưa xác nhận đã ngắt phiên Colab.")
        return result

    def inspect_pc_pairing(self, user_code: str) -> dict[str, Any]:
        return self._pc_request("POST", "/v1/pc/pairing/inspect", {"user_code": user_code.strip().upper()})

    def approve_pc_pairing(self, user_code: str, preview: dict) -> dict[str, Any]:
        body = {key: preview[key] for key in ("pairing_id", "worker_id")}
        body["user_code"] = user_code.strip().upper()
        result = self._pc_request("POST", "/v1/pc/pairing/approve", body)
        if result.get("status") != "approved" or result.get("worker_id") != preview["worker_id"]:
            raise GenerationError("Broker chưa xác nhận đúng máy đã duyệt.")
        return result

    def list_pc_devices(self) -> list[dict[str, Any]]:
        client = BrokerClient(self.options, no_redirect=True)
        payload = client._json_request("GET", "/v1/pc/devices")
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise GenerationError("Broker trả danh sách máy CPU không hợp lệ.")
        return payload

    def control_pc_device(self, worker_id: str, action: str) -> dict[str, Any]:
        return self._pc_request("POST", f"/v1/pc/devices/{quote(worker_id, safe='')}/control", {"action": action})

    def pc_statistics(self, worker_id: str, offset_minutes: int = 0) -> dict[str, Any]:
        return self._pc_request("GET", f"/v1/pc/devices/{quote(worker_id, safe='')}/stats?offset_minutes={offset_minutes}")

    def revoke_pc_device(self, worker_id: str) -> dict[str, Any]:
        return self._pc_request("POST", f"/v1/pc/devices/{quote(worker_id, safe='')}/revoke")

    def _pc_request(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        client = BrokerClient(self.options.model_copy(update={"max_retries": 0}), no_redirect=True)
        payload = client._json_request(method, path, payload=body)
        if not isinstance(payload, dict):
            raise GenerationError("Broker trả trạng thái máy CPU không hợp lệ.")
        return payload

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

    def get_job_by_idempotency(self, idempotency_key: str) -> RemoteTtsJob:
        encoded = quote(idempotency_key, safe="")
        return RemoteTtsJob.model_validate(
            self._json_request("GET", f"/v1/jobs/by-idempotency/{encoded}")
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
                self.cancel(job_id)
                from omni_tts_shared.errors import GenerationCancelled

                raise GenerationCancelled("Đã hủy tác vụ remote compute.")
            job = self.get_job(job_id)
            if job.status in TERMINAL_REMOTE_JOB_STATUSES:
                return job
            if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
                raise GenerationError(f"Hết thời gian chờ remote job {job_id}.")
            time.sleep(max(0.1, poll_interval_seconds))

    def download_result(self, job: RemoteTtsJob, destination: Path) -> Path:
        if job.result is None:
            raise GenerationError(f"Remote job {job.job_id} chưa có metadata kết quả.")
        body = self._request(
            "GET", f"/v1/jobs/{quote(job.job_id, safe='')}/result",
            timeout_seconds=max(180.0, self.options.request_timeout_seconds),
        )
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
        timeout_seconds: float | None = None,
    ) -> bytes:
        headers = {
            "Accept": "application/json, audio/wav",
            "User-Agent": "Colin-TTS-Studio/0.5",
        }
        if authenticated:
            headers.update(self._auth_headers())
        headers.update(extra_headers or {})
        attempts = self.options.max_retries + 1
        retryable = {502, 503, 504, 520, 521, 522, 523, 524}
        url = f"{self.options.base_url}{path}"
        request_timeout = (
            self.options.request_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                opening = self._opener.open if self._opener else urlopen
                with opening(request, timeout=request_timeout) as response:
                    return response.read()
            except HTTPError as exc:
                detail = _http_error_detail(exc)
                error_type = BrokerConnectionError if exc.code in retryable else GenerationError
                last_error = error_type(
                    f"Broker trả lỗi HTTP {exc.code}: {detail or exc.reason}"
                )
                if exc.code not in retryable or attempt + 1 >= attempts:
                    raise last_error from exc
            except (URLError, socket.timeout, TimeoutError, ConnectionError, IncompleteRead) as exc:
                last_error = BrokerConnectionError("Tạm mất kết nối broker trên PC.")
                if attempt + 1 >= attempts:
                    raise last_error from exc
        raise last_error or GenerationError(f"Không kết nối được broker {url}.")

    def _auth_headers(self) -> dict[str, str]:
        token = os.environ.get(self.options.auth_env, "").strip()
        token_file = self.options.auth_token_file
        if not token and token_file is not None:
            try:
                token = token_file.expanduser().read_text(encoding="utf-8").strip()
            except OSError:
                token = ""
        if not token:
            source = (
                f" hoặc file {token_file}"
                if token_file is not None
                else ""
            )
            raise ConfigError(
                f"Thiếu token trong biến môi trường {self.options.auth_env}{source}."
            )
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
