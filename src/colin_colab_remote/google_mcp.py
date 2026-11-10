"""Native HTTP adapter for Google's authenticated remote Colab MCP service."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

from .oauth import GoogleOAuth, NoRedirect, ProviderError


MCP_URL = "https://colaboratory.googleapis.com/mcp"
REST_URL = "https://colaboratory.googleapis.com/v1"
_RESOURCE_ID = r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
_MAX_RESPONSE = 16 * 1024 * 1024


def _ident(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(_RESOURCE_ID, value):
        raise ProviderError("invalid_request", "Mã runtime hoặc phiên Colab không hợp lệ.")
    return value


def _runtime_name(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("runtimes/"):
        raise ProviderError("invalid_request", "Tên runtime Colab không hợp lệ.")
    _ident(value[len("runtimes/"):])
    return value


def _error_fields(value) -> set[str]:
    """Read machine categories only. Provider messages may contain secrets."""
    fields: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"status", "reason", "code"} and isinstance(item, (str, int)):
                fields.add(str(item).upper())
            elif key == "text" and isinstance(item, str):
                try:
                    fields.update(_error_fields(json.loads(item)))
                except (ValueError, TypeError):
                    # Google's hosted MCP can return the canonical gRPC text
                    # without a structured error. Keep raw provider text private.
                    canonical = {
                        "Requested entity was not found.": "NOT_FOUND",
                        "Requested entity already exists.": "ALREADY_EXISTS",
                        "Precondition check failed.": "FAILED_PRECONDITION",
                    }
                    category = canonical.get(item.strip())
                    if category:
                        fields.add(category)
            elif isinstance(item, (dict, list)):
                fields.update(_error_fields(item))
    elif isinstance(value, list):
        for item in value:
            fields.update(_error_fields(item))
    return fields


def _provider_error(payload=None, *, http_status: int | None = None) -> ProviderError:
    fields = _error_fields(payload)
    if http_status == 401 or fields.intersection({"UNAUTHENTICATED", "INVALID_CREDENTIALS", "16", "401"}):
        return ProviderError("needs_auth", "Google yêu cầu đăng nhập hoặc cấp lại quyền Colab.")
    if fields.intersection({"SERVICE_DISABLED", "API_DISABLED", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}):
        return ProviderError("setup_required", "Cần bật Colab API/MCP và cấp đủ quyền cho ứng dụng Google.")
    if http_status == 403 or fields.intersection({"PERMISSION_DENIED", "7", "403"}):
        return ProviderError("permission_denied", "Google chưa cho tài khoản này thực hiện thao tác Colab.")
    if http_status == 404 or fields.intersection({"NOT_FOUND", "5", "404"}):
        return ProviderError("not_found", "Runtime hoặc phiên Colab không còn tồn tại.")
    if http_status == 429 or fields.intersection({"RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED", "TOO_MANY_ACTIVE_RUNTIMES", "8", "429"}):
        return ProviderError("quota", "Google đang giới hạn tài nguyên hoặc số yêu cầu của tài khoản này.", retryable=True)
    if http_status in (408, 504) or fields.intersection({"DEADLINE_EXCEEDED", "4", "408", "504"}):
        return ProviderError("timeout", "Chưa nhận được kết quả Colab trong thời gian chờ. Cần đối soát phiên hiện có trước khi thử lại.", retryable=True)
    if http_status in (502, 503) or fields.intersection({"UNAVAILABLE", "NO_AVAILABLE_BACKENDS", "OUT_OF_CAPACITY", "14", "502", "503"}):
        return ProviderError("unavailable", "Colab tạm chưa có tài nguyên hoặc chưa kết nối được.", retryable=True)
    if fields.intersection({"CANCELLED", "1"}):
        return ProviderError("cancelled", "Thao tác Colab đã được dừng.")
    if http_status == 409 or fields.intersection({"ALREADY_EXISTS", "6", "409"}):
        return ProviderError("already_exists", "Runtime Colab với mã này đã tồn tại, cần đối soát trước khi tiếp tục.")
    if http_status == 400 or fields.intersection({"INVALID_ARGUMENT", "3", "400"}):
        return ProviderError("invalid_request", "Google từ chối tham số của thao tác Colab.")
    if fields.intersection({"FAILED_PRECONDITION", "9"}):
        return ProviderError("precondition", "Tài khoản hoặc runtime chưa đáp ứng điều kiện Google yêu cầu.")
    return ProviderError("provider_error", "Colab chưa hoàn tất thao tác. Kiểm tra trạng thái trước khi thử lại.", retryable=http_status is not None and http_status >= 500)


class GoogleColabProvider:
    """No browser is opened. Resource ownership and retry policy belong to the caller."""

    def __init__(self, data_dir: Path, account_id: str = "google-pro-1", *,
                 allow_unencrypted: bool = False, request_timeout: float = 30,
                 execution_timeout: float = 90):
        self.oauth = GoogleOAuth(Path(data_dir), account_id, allow_unencrypted=allow_unencrypted)
        self.account_id = account_id
        self.request_timeout = min(max(request_timeout, 1), 120)
        self.execution_timeout = min(max(execution_timeout, 1), 600)
        self.on_progress = None
        self.cancel_event: threading.Event | None = None
        self._opener = build_opener(NoRedirect())

    def configure_client(self, path: Path) -> dict:
        return self.oauth.configure_client(path)

    def begin_auth(self):
        return self.oauth.begin_auth()

    def auth_status(self) -> dict:
        return self.oauth.status()

    def _cancelled(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ProviderError("cancelled", "Thao tác Colab đã được dừng.")

    def _request(self, method: str, url: str, payload: dict | None = None,
                 *, timeout: float | None = None) -> dict:
        self._cancelled()
        token = self.oauth.access_token()
        headers = {"Accept": "application/json, text/event-stream",
                   "Authorization": "Bearer " + token,
                   "User-Agent": "Colin-Colab-Remote/1"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        timeout = timeout or self.request_timeout
        # A 401 is rejected before execution. Only that response permits one token refresh.
        for attempt in range(2):
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    return self._read_response(response, timeout)
            except HTTPError as error:
                status = error.code
                raw = error.read(65536)
                error.close()
                if status == 401 and attempt == 0:
                    request.add_header("Authorization", "Bearer " + self.oauth.access_token(force_refresh=True))
                    continue
                try:
                    details = json.loads(raw)
                except (ValueError, UnicodeError):
                    details = None
                raise _provider_error(details, http_status=status) from None
            except TimeoutError:
                raise _provider_error({"status": "DEADLINE_EXCEEDED"}) from None
            except (URLError, OSError):
                raise ProviderError("unavailable", "Kết nối Colab bị gián đoạn. Cần đối soát runtime hiện có trước khi thử lại.", retryable=True) from None
        raise ProviderError("needs_auth", "Google cần xác thực lại.")

    def _read_response(self, response, timeout: float) -> dict:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/event-stream" not in content_type:
            data = response.read(_MAX_RESPONSE + 1)
            if len(data) > _MAX_RESPONSE:
                raise ProviderError("provider_error", "Phản hồi Colab vượt giới hạn cho phép.")
            try:
                result = json.loads(data or b"{}")
            except (ValueError, UnicodeError):
                raise ProviderError("provider_error", "Colab trả về phản hồi không hợp lệ.") from None
            if not isinstance(result, dict):
                raise ProviderError("provider_error", "Colab trả về phản hồi không hợp lệ.")
            return result
        deadline = time.monotonic() + timeout
        size = 0
        lines: list[str] = []
        while True:
            self._cancelled()
            if time.monotonic() > deadline:
                raise _provider_error({"status": "DEADLINE_EXCEEDED"})
            line = response.readline(_MAX_RESPONSE + 1)
            size += len(line)
            if size > _MAX_RESPONSE:
                raise ProviderError("provider_error", "Luồng phản hồi Colab vượt giới hạn cho phép.")
            if not line or line.strip() == b"":
                if lines:
                    try:
                        message = json.loads("\n".join(lines))
                    except (ValueError, UnicodeError):
                        raise ProviderError("provider_error", "Colab trả về sự kiện không hợp lệ.") from None
                    lines = []
                    if isinstance(message, dict):
                        if "result" in message or "error" in message:
                            return message
                        if callable(self.on_progress):
                            self.on_progress(message)
                if not line:
                    raise ProviderError("timeout", "Luồng Colab kết thúc trước khi xác nhận kết quả. Cần đối soát phiên hiện có.", retryable=True)
                continue
            if line.startswith(b"data:"):
                try:
                    lines.append(line[5:].decode("utf-8").strip())
                except UnicodeError:
                    raise ProviderError("provider_error", "Colab trả về sự kiện không hợp lệ.") from None

    @staticmethod
    def _tool_value(envelope: dict):
        if "error" in envelope:
            raise _provider_error(envelope["error"])
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise ProviderError("provider_error", "Colab chưa trả kết quả của công cụ.")
        structured = result.get("structuredContent", result.get("structured_content"))
        if result.get("isError"):
            raise _provider_error(result)
        if isinstance(structured, (dict, list)):
            return structured
        texts = [item["text"] for item in result.get("content", [])
                 if item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not texts:
            return {}
        try:
            value = json.loads("\n".join(texts))
        except (ValueError, TypeError):
            raise ProviderError("provider_error", "Công cụ Colab chưa trả dữ liệu có cấu trúc.") from None
        if not isinstance(value, (dict, list)):
            raise ProviderError("provider_error", "Công cụ Colab chưa trả dữ liệu có cấu trúc.")
        return value

    def _call(self, tool: str, arguments: dict, *, timeout: float | None = None):
        request_id = str(uuid.uuid4())
        params = {"name": tool, "arguments": arguments}
        if tool == "execute_code":
            params["_meta"] = {"progressToken": request_id}
        response = self._request("POST", MCP_URL, {
            "jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": params,
        }, timeout=timeout)
        return self._tool_value(response)

    def get_subscription(self) -> dict:
        return self._call("get_subscription", {})

    def list_runtime_specs(self) -> list[dict]:
        value = self._call("list_runtime_specs", {})
        specs = value.get("runtimeSpecs", []) if isinstance(value, dict) else value
        if not isinstance(specs, list) or not all(isinstance(item, dict) for item in specs):
            raise ProviderError("provider_error", "Danh sách cấu hình Colab không hợp lệ.")
        return specs

    def list_runtimes(self) -> list[dict]:
        value = self._call("list_runtimes", {})
        runtimes = value.get("runtimes", []) if isinstance(value, dict) else value
        if not isinstance(runtimes, list) or not all(isinstance(item, dict) for item in runtimes):
            raise ProviderError("provider_error", "Danh sách runtime Colab không hợp lệ.")
        return runtimes

    def create_runtime(self, runtime_id: str, request_id: str, spec: dict) -> dict:
        _ident(runtime_id)
        try:
            parsed = uuid.UUID(request_id)
            if parsed.version != 4:
                raise ValueError("UUID4 required")
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("invalid_request", "Cần lưu mã yêu cầu UUID4 trước khi cấp runtime.") from None
        key = spec.get("key", spec) if isinstance(spec, dict) else {}
        if not isinstance(key, dict) or not all(isinstance(key.get(k), str) and key[k]
                                               for k in ("variant", "accelerator", "shape")):
            raise ProviderError("invalid_request", "Cần chọn một cấu hình Colab đã được xác nhận phù hợp.")
        runtime = self._call("create_runtime", {
            "runtimeId": runtime_id, "requestId": str(parsed),
            "runtime": {"runtimeSpec": {k: key[k] for k in ("variant", "accelerator", "shape")}},
        }, timeout=max(self.request_timeout, 120))
        if isinstance(runtime, dict) and ("done" in runtime or str(runtime.get("name", "")).startswith("operations/")):
            runtime = self._wait_operation(runtime)
        if not isinstance(runtime, dict) or runtime.get("name") != "runtimes/" + runtime_id:
            raise ProviderError("provider_error", "Colab chưa xác nhận đúng runtime được yêu cầu. Cần đối soát trước khi tiếp tục.")
        return runtime

    def _wait_operation(self, operation: dict) -> dict:
        deadline = time.monotonic() + 90
        while not operation.get("done"):
            self._cancelled()
            name = operation.get("name", "")
            if not re.fullmatch(r"operations/[a-zA-Z0-9/_-]+", name):
                raise ProviderError("provider_error", "Mã thao tác Colab không hợp lệ.")
            if time.monotonic() >= deadline:
                raise _provider_error({"status": "DEADLINE_EXCEEDED"})
            time.sleep(0.5)
            operation = self._request("GET", REST_URL + "/" + quote(name, safe="/"))
        if operation.get("error"):
            raise _provider_error(operation["error"])
        value = operation.get("response")
        if not isinstance(value, dict):
            raise ProviderError("provider_error", "Colab chưa trả runtime của thao tác đã hoàn tất.")
        return value

    def get_runtime(self, name: str) -> dict:
        return self._call("get_runtime", {"name": _runtime_name(name)})

    def create_session(self, runtime_name: str, session_id: str) -> dict:
        _runtime_name(runtime_name)
        _ident(session_id)
        expected = runtime_name + "/sessions/" + session_id
        try:
            session = self._call("create_session", {"parent": runtime_name, "sessionId": session_id})
        except ProviderError as error:
            if error.code not in {"already_exists", "timeout", "unavailable"}:
                raise
            try:
                matches = [item for item in self.list_sessions(runtime_name) if item.get("name") == expected]
            except ProviderError:
                raise error from None
            if len(matches) == 1:
                return matches[0]
            raise
        if not isinstance(session, dict) or session.get("name") != expected:
            raise ProviderError("provider_error", "Colab chưa xác nhận đúng phiên Jupyter được yêu cầu.")
        return session

    def list_sessions(self, runtime_name: str) -> list[dict]:
        value = self._call("list_sessions", {"parent": _runtime_name(runtime_name)})
        sessions = value.get("sessions", []) if isinstance(value, dict) else value
        if not isinstance(sessions, list) or not all(isinstance(item, dict) for item in sessions):
            raise ProviderError("provider_error", "Danh sách phiên Jupyter Colab không hợp lệ.")
        return sessions

    def execute(self, code: str, session: str, execution_id: str) -> dict:
        if not isinstance(session, str) or not re.fullmatch(r"runtimes/" + _RESOURCE_ID + r"/sessions/" + _RESOURCE_ID, session):
            raise ProviderError("invalid_request", "Cần dùng phiên Jupyter cố định để đối soát lần thực thi.")
        try:
            uuid.UUID(execution_id)
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("invalid_request", "Mã thực thi Colab phải là UUID.") from None
        if not isinstance(code, str) or not code:
            raise ProviderError("invalid_request", "Chưa có lệnh để thực thi trên Colab.")
        result = self._call("execute_code", {"code": code, "session": session,
                                            "executionId": execution_id}, timeout=self.execution_timeout)
        if not isinstance(result, dict):
            raise ProviderError("provider_error", "Colab chưa trả kết quả thực thi.")
        if result.get("executionError"):
            raise ProviderError("execution_error", "Lệnh trên Colab gặp lỗi. Xem trạng thái bootstrap hoặc worker để khôi phục.")
        return result

    def delete_runtime(self, name: str) -> dict:
        _runtime_name(name)
        self._call("delete_runtime", {"name": name, "allowMissing": True})
        deadline = time.monotonic() + 30
        while True:
            try:
                self.get_runtime(name)
            except ProviderError as error:
                if error.code == "not_found":
                    return {"name": name, "released": True}
                raise
            if time.monotonic() >= deadline:
                raise ProviderError("cleanup_pending", "Google chưa xác nhận đã trả runtime. Cần đối soát lại.", retryable=True)
            self._cancelled()
            time.sleep(0.5)
