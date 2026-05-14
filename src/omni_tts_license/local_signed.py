from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from omni_tts_license.machine_id import current_device_id
from omni_tts_license.models import LicenseData, LicenseStatus
from omni_tts_license.store import install_license as copy_license
from omni_tts_license.store import license_path


class LocalSignedLicenseProvider:
    def __init__(
        self,
        public_key_path: str | Path | None = None,
        installed_license_path: str | Path | None = None,
    ) -> None:
        self.public_key_path = Path(public_key_path) if public_key_path else _default_public_key_path()
        self.installed_license_path = (
            Path(installed_license_path) if installed_license_path else license_path()
        )

    def current_device_id(self) -> str:
        return current_device_id()

    def install_license(self, source_path: str | Path) -> LicenseStatus:
        copy_license(source_path)
        return self.get_status()

    def is_feature_enabled(self, feature: str) -> bool:
        return self.get_status().feature_enabled(feature)

    def get_status(self) -> LicenseStatus:
        if not self.public_key_path.exists():
            return self._status(
                False,
                "public_key_missing",
                "Chưa cấu hình khóa công khai để kiểm tra bản quyền.",
            )
        if not self.installed_license_path.exists():
            return self._status(
                False,
                "license_missing",
                "Chưa kích hoạt bản quyền. Hãy nhập file license.",
            )

        try:
            data = json.loads(self.installed_license_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return self._status(False, "license_unreadable", "Không đọc được file license.")

        signature = data.get("signature")
        if not isinstance(signature, str) or not signature:
            return self._status(False, "signature_missing", "License thiếu chữ ký.")

        signed_payload = {key: value for key, value in data.items() if key != "signature"}
        if not self._verify_signature(signed_payload, signature):
            return self._status(
                False,
                "signature_invalid",
                "License không hợp lệ hoặc đã bị chỉnh sửa.",
            )

        email = _string_or_none(data.get("email"))
        plan = _string_or_none(data.get("plan"))
        device_id = _string_or_none(data.get("device_id"))
        expires_at = _parse_expiry(data.get("expires_at"))
        features = _parse_features(data.get("features"))

        if expires_at is None:
            return self._status(False, "expires_at_invalid", "Ngày hết hạn license không hợp lệ.")
        if expires_at < datetime.now():
            return self._status(
                False,
                "expired",
                f"License đã hết hạn lúc {_format_expiry(expires_at)}.",
                email=email,
                plan=plan,
                expires_at=expires_at,
                device_id=device_id,
                features=features,
            )
        current_id = self.current_device_id()
        if device_id and device_id != current_id:
            return self._status(
                False,
                "device_mismatch",
                "License không thuộc máy này.",
                email=email,
                plan=plan,
                expires_at=expires_at,
                device_id=device_id,
                features=features,
            )
        return self._status(
            True,
            "valid",
            f"Đã kích hoạt cho {email or 'người dùng'}, còn hạn đến {_format_expiry(expires_at)}.",
            email=email,
            plan=plan,
            expires_at=expires_at,
            device_id=device_id,
            features=features,
        )

    def _verify_signature(self, payload: LicenseData, signature: str) -> bool:
        try:
            public_key = serialization.load_pem_public_key(
                self.public_key_path.read_bytes()
            )
            public_key.verify(
                _urlsafe_b64decode(signature),
                canonical_payload(payload),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError, TypeError, OSError):
            return False
        return True

    def _status(
        self,
        valid: bool,
        code: str,
        message: str,
        *,
        email: str | None = None,
        plan: str | None = None,
        expires_at: datetime | None = None,
        device_id: str | None = None,
        features: dict[str, bool] | None = None,
    ) -> LicenseStatus:
        return LicenseStatus(
            valid=valid,
            code=code,
            message=message,
            email=email,
            plan=plan,
            expires_at=expires_at,
            device_id=device_id,
            features=features or {},
            license_path=self.installed_license_path,
        )


def canonical_payload(payload: LicenseData) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(private_key_pem: bytes, payload: LicenseData) -> str:
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(
        canonical_payload(payload),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return _urlsafe_b64encode(signature)


def _default_public_key_path() -> Path:
    env_path = os.environ.get("OMNI_TTS_LICENSE_PUBLIC_KEY")
    if env_path:
        return Path(env_path)
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "config" / "license_public_key.pem"


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding_len = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding_len))


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_expiry(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        if "T" not in normalized and " " not in normalized:
            return datetime.combine(datetime.strptime(normalized, "%Y-%m-%d").date(), time.max)
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _format_expiry(value: datetime) -> str:
    if value.time() == time.max:
        return value.date().isoformat()
    return value.strftime("%Y-%m-%d %H:%M")


def _parse_features(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {str(key): bool(item) for key, item in value.items()}
