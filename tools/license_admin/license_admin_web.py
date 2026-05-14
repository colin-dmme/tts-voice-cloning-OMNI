from __future__ import annotations

import argparse
import json
import re
import sys
import webbrowser
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from omni_tts_license.local_signed import sign_payload


DEFAULT_PRIVATE_KEY = PROJECT_ROOT / "secrets" / "license_private_key.pem"
ADMIN_HTML = Path(__file__).with_name("admin.html")
DEFAULT_FEATURES = {
    "tts": True,
    "batch_export": True,
    "vieneu": True,
    "qwen": False,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web UI for issuing Omni TTS licenses")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), LicenseAdminHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"License admin is running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class LicenseAdminHandler(BaseHTTPRequestHandler):
    server_version = "OmniTTSLicenseAdmin/1.0"

    def do_GET(self) -> None:
        if self.path in {"/", "/admin.html"}:
            self._send_file(ADMIN_HTML, "text/html; charset=utf-8")
            return
        if self.path == "/api/defaults":
            self._send_json(
                {
                    "privateKey": str(DEFAULT_PRIVATE_KEY),
                    "expiresAt": (datetime.now() + timedelta(days=365)).replace(
                        hour=23,
                        minute=59,
                        second=0,
                        microsecond=0,
                    ).isoformat(timespec="minutes"),
                    "plan": "basic",
                    "features": DEFAULT_FEATURES,
                }
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/issue":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            request = self._read_json()
            license_json, filename = create_license(request)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self._send_json(
                {"error": f"Lỗi khi tạo license: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json({"filename": filename, "license_json": license_json})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Thiếu dữ liệu gửi lên.")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Dữ liệu gửi lên không phải JSON hợp lệ.") from exc
        if not isinstance(data, dict):
            raise ValueError("Dữ liệu gửi lên không hợp lệ.")
        return data

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_license(request: dict[str, Any]) -> tuple[str, str]:
    private_key = _path_value(request.get("private_key")) or DEFAULT_PRIVATE_KEY
    email = _required_text(request.get("email"), "Email khách")
    expires_at = _required_text(request.get("expires_at"), "Ngày hết hạn")
    device_id = _required_text(request.get("device_id"), "Mã máy").upper()
    plan = _required_text(request.get("plan"), "Gói")
    features = _features_value(request.get("features"))

    if not private_key.exists():
        raise ValueError(f"Không tìm thấy private key: {private_key}")
    if not private_key.is_file():
        raise ValueError(f"Private key không phải file: {private_key}")
    expires_at = _normalize_expiry(expires_at)
    if len(device_id) < 8:
        raise ValueError("Mã máy quá ngắn hoặc chưa đúng.")

    payload = {
        "email": email,
        "expires_at": expires_at,
        "plan": plan,
        "device_id": device_id,
        "features": features,
    }
    payload["signature"] = sign_payload(private_key.read_bytes(), payload)
    license_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    filename = _license_filename(email, expires_at)
    return license_json, filename


def _path_value(value: Any) -> Path | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    return Path(text) if text else None


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Vui lòng nhập {label.lower()}.")
    return text


def _features_value(value: Any) -> dict[str, bool]:
    features = dict(DEFAULT_FEATURES)
    if value is None:
        return features
    if not isinstance(value, dict):
        raise ValueError("Danh sách tính năng không hợp lệ.")
    for key, enabled in value.items():
        features[str(key)] = bool(enabled)
    return features


def _normalize_expiry(value: str) -> str:
    normalized = value.strip().replace(" ", "T")
    try:
        if "T" in normalized:
            return datetime.fromisoformat(normalized).isoformat(timespec="minutes")
        return datetime.strptime(normalized, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("Ngày giờ hết hạn không hợp lệ.") from exc


def _license_filename(email: str, expires_at: str) -> str:
    expires_at = expires_at.replace(":", "-")
    safe_email = re.sub(r"[^A-Za-z0-9._-]+", "_", email).strip("._-")
    if not safe_email:
        safe_email = "customer"
    return f"license_{safe_email}_{expires_at}.json"


if __name__ == "__main__":
    main()
