"""Per-account Google Desktop OAuth with protected local credential storage."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
COLAB_SCOPE = "https://www.googleapis.com/auth/colaboratory"
SCOPES = ("openid", "email", COLAB_SCOPE)
_DPAPI_PREFIX = b"COLIN-COLAB-DPAPI-1\n"
_PLAIN_PREFIX = b"COLIN-COLAB-PRIVATE-1\n"


class ProviderError(RuntimeError):
    """A stable error category whose message is safe for UI and job logs."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    if decrypt:
        call = crypt.CryptUnprotectData
        call.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = call(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        call = crypt.CryptProtectData
        call.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = call(ctypes.byref(source), "Colin Colab OAuth", None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise ProviderError("credential_store", "Windows không thể mở hoặc bảo vệ thông tin Google của tài khoản này.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, wintypes.HLOCAL))


class GoogleOAuth:
    """User OAuth only. Starting consent creates a callback listener, never a browser."""

    def __init__(self, data_dir: Path, account_id: str = "google-pro-1", *,
                 allow_unencrypted: bool = False):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", account_id):
            raise ValueError("account_id must contain lowercase letters, digits or hyphens")
        self.account_id = account_id
        self.directory = Path(data_dir) / "accounts" / account_id
        self.path = self.directory / "google-oauth.dat"
        self.allow_unencrypted = allow_unencrypted
        self._mutex = threading.RLock()
        self._opener = build_opener(NoRedirect())

    @contextmanager
    def _locked(self):
        with self._mutex:
            self.directory.mkdir(parents=True, exist_ok=True)
            lock_path = self.directory / "google-oauth.lock"
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            handle = os.fdopen(descriptor, "r+b")
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            deadline = time.monotonic() + 10
            acquired = False
            try:
                while not acquired:
                    handle.seek(0)
                    try:
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise ProviderError("busy", "Thông tin Google đang được một thao tác khác sử dụng.", retryable=True) from None
                        time.sleep(0.05)
                yield
            finally:
                if acquired:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    def _read(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            data = self.path.read_bytes()
            if len(data) > 1024 * 1024:
                raise ValueError("oversized credentials")
            if data.startswith(_DPAPI_PREFIX) and os.name == "nt":
                payload = _dpapi(data[len(_DPAPI_PREFIX):], decrypt=True)
            elif data.startswith(_PLAIN_PREFIX) and self.allow_unencrypted:
                payload = data[len(_PLAIN_PREFIX):]
            else:
                raise ValueError("unsupported protection")
            result = json.loads(payload)
            if not isinstance(result, dict) or result.get("account_id") != self.account_id:
                raise ValueError("wrong account")
            return result
        except (OSError, ValueError, UnicodeError):
            raise ProviderError("credential_store", "Không đọc được thông tin Google đã lưu của tài khoản này.") from None

    def _write(self, record: dict) -> None:
        payload = json.dumps({**record, "account_id": self.account_id}, ensure_ascii=False).encode("utf-8")
        if os.name == "nt":
            data = _DPAPI_PREFIX + _dpapi(payload)
        elif self.allow_unencrypted:
            data = _PLAIN_PREFIX + payload
        else:
            raise ProviderError("credential_store", "Cần kho khóa Windows hoặc cho phép rõ ràng tệp riêng trên hệ điều hành này.")
        temporary = self.path.with_name(self.path.name + "." + secrets.token_hex(8) + ".tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise ProviderError("credential_store", "Không lưu được thông tin Google của tài khoản này.") from None
        finally:
            temporary.unlink(missing_ok=True)

    def configure_client(self, path: Path) -> dict:
        try:
            if Path(path).stat().st_size > 1024 * 1024:
                raise ValueError("oversized config")
            config = json.loads(Path(path).read_text(encoding="utf-8-sig"))["installed"]
            client_id = config["client_id"]
            client_secret = config["client_secret"]
            if not isinstance(client_id, str) or not client_id.endswith(".apps.googleusercontent.com"):
                raise ValueError("invalid desktop client")
            if not isinstance(client_secret, str) or not client_secret or len(client_secret) > 4096:
                raise ValueError("invalid secret")
            if config.get("token_uri", TOKEN_URL) not in (TOKEN_URL, "https://accounts.google.com/o/oauth2/token"):
                raise ValueError("untrusted token endpoint")
            if config.get("auth_uri", AUTH_URL) not in (AUTH_URL, "https://accounts.google.com/o/oauth2/auth"):
                raise ValueError("untrusted auth endpoint")
        except (OSError, ValueError, TypeError, KeyError):
            raise ProviderError("invalid_client", "Chọn tệp OAuth JSON của ứng dụng Desktop đã đăng ký với Google.") from None
        with self._locked():
            record = self._read()
            if record.get("client_id") != client_id:
                record = {}
            record.update(client_id=client_id, client_secret=client_secret)
            self._write(record)
        return self.status()

    def status(self) -> dict:
        with self._locked():
            record = self._read()
        configured = bool(record.get("client_id"))
        authorized = bool(record.get("refresh_token")) and not record.get("auth_required", False)
        return {"account_id": self.account_id, "configured": configured,
                "authorized": authorized, "state": "ready" if authorized else "needs_auth",
                "email": record.get("email", "")}

    def begin_auth(self, *, timeout_seconds: float = 300) -> "OAuthSession":
        with self._locked():
            record = self._read()
        if not record.get("client_id"):
            raise ProviderError("needs_auth", "Nhập cấu hình OAuth Desktop trước khi đăng nhập Google.")
        return OAuthSession(self, record, timeout_seconds=timeout_seconds)

    def _json_request(self, url: str, *, form: dict | None = None, token: str = "") -> dict:
        headers = {"Accept": "application/json", "User-Agent": "Colin-Colab-Remote/1"}
        data = None
        if form is not None:
            data = urlencode(form).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            with self._opener.open(Request(url, data=data, headers=headers), timeout=20) as response:
                body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError("oversized response")
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("invalid response")
            return value
        except HTTPError as error:
            status = error.code
            error.close()
            if status in (400, 401, 403):
                raise ProviderError("needs_auth", "Google cần xác thực lại hoặc cấp đủ quyền Colab.") from None
            raise ProviderError("unavailable", "Dịch vụ xác thực Google chưa phản hồi, hãy thử lại sau.", retryable=True) from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("unavailable", "Chưa kết nối được dịch vụ xác thực Google.", retryable=True) from None
        except (ValueError, UnicodeError):
            raise ProviderError("provider_error", "Google trả về dữ liệu xác thực không hợp lệ.") from None

    @staticmethod
    def _apply_token(record: dict, response: dict) -> None:
        access_token = response.get("access_token")
        expires_in = response.get("expires_in", 3600)
        if not isinstance(access_token, str) or not access_token or len(access_token) > 16384:
            raise ProviderError("needs_auth", "Google chưa cấp khóa truy cập hợp lệ.")
        if response.get("token_type", "Bearer").lower() != "bearer":
            raise ProviderError("needs_auth", "Google chưa cấp kiểu xác thực được hỗ trợ.")
        try:
            lifetime = float(expires_in)
            if not 0 < lifetime <= 86400:
                raise ValueError("invalid expiry")
        except (ValueError, TypeError):
            raise ProviderError("provider_error", "Google trả về thời hạn xác thực không hợp lệ.") from None
        if response.get("scope") and COLAB_SCOPE not in response["scope"].split():
            raise ProviderError("needs_auth", "Cần cấp quyền Colab cho ứng dụng.")
        record.update(access_token=access_token, expires_at=time.time() + lifetime, auth_required=False)
        refresh = response.get("refresh_token")
        if refresh:
            record["refresh_token"] = refresh

    def access_token(self, *, force_refresh: bool = False) -> str:
        with self._locked():
            record = self._read()
            if not record.get("refresh_token") or record.get("auth_required"):
                raise ProviderError("needs_auth", "Đăng nhập Google và cấp quyền Colab cho tài khoản này.")
            if not force_refresh and record.get("access_token") and record.get("expires_at", 0) > time.time() + 60:
                return record["access_token"]
            try:
                response = self._json_request(TOKEN_URL, form={
                    "client_id": record["client_id"], "client_secret": record["client_secret"],
                    "refresh_token": record["refresh_token"], "grant_type": "refresh_token",
                })
                self._apply_token(record, response)
            except ProviderError as error:
                if error.code == "needs_auth":
                    record.update(auth_required=True, access_token="", expires_at=0)
                    self._write(record)
                raise
            self._write(record)
            return record["access_token"]

    def _complete_auth(self, client: dict, code: str, verifier: str, callback: str,
                       still_active) -> None:
        response = self._json_request(TOKEN_URL, form={
            "client_id": client["client_id"], "client_secret": client["client_secret"],
            "code": code, "code_verifier": verifier, "redirect_uri": callback,
            "grant_type": "authorization_code",
        })
        token_record: dict = {}
        self._apply_token(token_record, response)
        identity = self._json_request(USERINFO_URL, token=token_record["access_token"])
        subject = identity.get("sub")
        if not isinstance(subject, str) or not subject or identity.get("email_verified") is not True:
            raise ProviderError("needs_auth", "Chưa xác minh được danh tính Google vừa đăng nhập.")
        with self._locked():
            record = self._read()
            if not still_active() or record.get("client_id") != client["client_id"]:
                raise ProviderError("cancelled", "Phiên xác thực đã kết thúc hoặc cấu hình đã đổi.")
            if record.get("subject") and record["subject"] != subject:
                raise ProviderError("wrong_account", "Tài khoản Google vừa chọn khác với tài khoản đã liên kết. Hãy chọn lại đúng tài khoản.")
            record.update(token_record, subject=subject, email=identity.get("email", ""))
            if not record.get("refresh_token"):
                raise ProviderError("needs_auth", "Google chưa cấp quyền dùng khi chạy nền, hãy đăng nhập và cấp quyền lại.")
            self._write(record)


class OAuthSession:
    """A bounded PKCE loopback flow that the UI can display and poll."""

    def __init__(self, oauth: GoogleOAuth, client: dict, *, timeout_seconds: float = 300):
        self.state = secrets.token_urlsafe(32)
        self._verifier = secrets.token_urlsafe(64)
        self._deadline = time.monotonic() + min(max(timeout_seconds, 1), 900)
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._status = {"state": "pending", "code": "", "message": "Chờ bạn cấp quyền Google."}
        session = self

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                supplied_state = query.get("state", [""])[0]
                if parsed.path != "/oauth/callback" or not hmac.compare_digest(supplied_state, session.state):
                    self._reply(400, "Invalid authorization response. Return to Colin TTS Studio.")
                    return
                with session._lock:
                    if session._closed.is_set() or session._status["state"] != "pending":
                        self._reply(409, "Authorization response already received.")
                        return
                    session._status["state"] = "exchanging"
                code = query.get("code", [""])[0]
                try:
                    if query.get("error") or not code or len(code) > 16384:
                        raise ProviderError("needs_auth", "Google chưa được cấp quyền. Bạn có thể bắt đầu đăng nhập lại.")
                    oauth._complete_auth(client, code, session._verifier, session.callback_url,
                                         lambda: not session._closed.is_set())
                    session._finish("complete", "", "Đã liên kết tài khoản Google.")
                    self._reply(200, "Google account connected. You can return to Colin TTS Studio.")
                except ProviderError as error:
                    session._finish("needs_auth", error.code, str(error))
                    self._reply(400, "Authorization needs attention. Return to Colin TTS Studio.")
                except Exception:
                    session._finish("error", "provider_error", "Không hoàn tất được xác thực Google.")
                    self._reply(500, "Authorization could not finish. Return to Colin TTS Studio.")

            def _reply(self, status: int, message: str):
                payload = message.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Callback)
        except OSError:
            raise ProviderError("unavailable", "Không mở được cổng xác thực cục bộ.", retryable=True) from None
        self._server.daemon_threads = True
        self._server.timeout = 0.25
        self.callback_url = f"http://127.0.0.1:{self._server.server_port}/oauth/callback"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        self.url = AUTH_URL + "?" + urlencode({
            "client_id": client["client_id"], "redirect_uri": self.callback_url,
            "response_type": "code", "scope": " ".join(SCOPES), "state": self.state,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "select_account consent",
        })
        self._thread = threading.Thread(target=self._serve, name="colab-oauth-callback", daemon=True)
        self._thread.start()

    def _finish(self, state: str, code: str, message: str):
        with self._lock:
            if self._closed.is_set():
                return
            self._status = {"state": state, "code": code, "message": message}
            self._closed.set()

    def _serve(self):
        try:
            while not self._closed.is_set():
                if time.monotonic() >= self._deadline:
                    self._finish("expired", "needs_auth", "Phiên đăng nhập đã hết hạn. Bắt đầu lại khi bạn sẵn sàng.")
                    break
                self._server.handle_request()
        finally:
            self._server.server_close()

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def close(self) -> None:
        self._finish("cancelled", "cancelled", "Đã đóng phiên đăng nhập.")
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=0.5)
