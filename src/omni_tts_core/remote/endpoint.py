from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from omni_tts_shared.errors import ConfigError, GenerationError
from omni_tts_shared.schemas import RemoteEndpointOptions


@dataclass(frozen=True)
class EndpointPaths:
    root_url: str
    speech_url: str
    models_url: str
    health_url: str


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    headers: dict[str, str]
    status: int


class RemoteEndpointTransport:
    """Small HTTP transport independent of any specific TTS model protocol."""

    def __init__(self, options: RemoteEndpointOptions) -> None:
        self.options = options
        self.paths = endpoint_paths(options.base_url)

    def get_json(self, url: str) -> object:
        response = self.get(url)
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenerationError(f"Endpoint trả về JSON không hợp lệ: {url}") from exc

    def get(self, url: str) -> HttpResponse:
        return self._request("GET", url)

    def post_json(self, url: str, payload: dict) -> HttpResponse:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request(
            "POST",
            url,
            body=body,
            extra_headers={"Content-Type": "application/json"},
            timeout=self.options.request_timeout_seconds,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        headers = {"Accept": "application/json, audio/*"}
        headers.update(self._auth_headers())
        headers.update(extra_headers or {})
        retryable = {502, 503, 504, 520, 521, 522, 523, 524}
        attempts = self.options.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(
                    request,
                    timeout=timeout or self.options.connect_timeout_seconds,
                ) as response:
                    return HttpResponse(
                        body=response.read(),
                        headers={key.lower(): value for key, value in response.headers.items()},
                        status=int(response.status),
                    )
            except HTTPError as exc:
                detail = _error_detail(exc)
                last_error = GenerationError(
                    f"Endpoint trả lỗi HTTP {exc.code}: {detail or exc.reason}"
                )
                if exc.code not in retryable or attempt + 1 >= attempts:
                    raise last_error from exc
            except (URLError, socket.timeout, TimeoutError) as exc:
                last_error = GenerationError(
                    f"Không kết nối được endpoint {url}: {_network_detail(exc)}"
                )
                if attempt + 1 >= attempts:
                    raise last_error from exc
        raise last_error or GenerationError(f"Không kết nối được endpoint {url}.")

    def _auth_headers(self) -> dict[str, str]:
        if self.options.auth_mode == "none":
            return {}
        if self.options.auth_mode == "bearer_env":
            token = os.environ.get(self.options.auth_env, "").strip()
            if not token:
                raise ConfigError(
                    f"Thiếu token trong biến môi trường {self.options.auth_env}."
                )
            return {"Authorization": f"Bearer {token}"}
        raise ConfigError(f"Kiểu xác thực chưa được hỗ trợ: {self.options.auth_mode}")


def endpoint_paths(value: str) -> EndpointPaths:
    text = str(value or "").strip().rstrip("/")
    if not text:
        raise ConfigError(
            "Chưa nhập URL Higgs Remote. Hãy dán URL mới từ máy chủ/TryCloudflare."
        )
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ConfigError("URL endpoint phải bắt đầu bằng http:// hoặc https://.")
    path = parts.path.rstrip("/")
    suffix = "/v1/audio/speech"
    root_path = path[: -len(suffix)] if path.endswith(suffix) else path
    root = urlunsplit((parts.scheme, parts.netloc, root_path.rstrip("/"), "", "")).rstrip("/")
    return EndpointPaths(
        root_url=root,
        speech_url=f"{root}/v1/audio/speech",
        models_url=f"{root}/v1/models",
        health_url=f"{root}/health",
    )


def _error_detail(error: HTTPError) -> str:
    try:
        payload = error.read(4096).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload[:500]
    if isinstance(parsed, dict):
        detail = parsed.get("detail") or parsed.get("error") or parsed.get("message")
        return str(detail or parsed)[:500]
    return str(parsed)[:500]


def _network_detail(error: Exception) -> str:
    reason = getattr(error, "reason", error)
    return str(reason)[:500]
