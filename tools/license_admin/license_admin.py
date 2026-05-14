from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from omni_tts_license.local_signed import sign_payload
from omni_tts_license.machine_id import current_device_id


DEFAULT_FEATURES = {
    "tts": True,
    "batch_export": True,
    "vieneu": True,
    "qwen": False,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Omni TTS local license admin tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_keys = subparsers.add_parser("init-keys", help="Create an RSA key pair")
    init_keys.add_argument("--private-key", required=True)
    init_keys.add_argument("--public-key", required=True)

    issue = subparsers.add_parser("issue", help="Issue a signed license.json")
    issue.add_argument("--private-key", required=True)
    issue.add_argument("--email", required=True)
    issue.add_argument("--expires-at", required=True, help="YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    issue.add_argument("--device-id", required=True)
    issue.add_argument("--plan", default="basic")
    issue.add_argument("--output", required=True)
    issue.add_argument(
        "--feature",
        action="append",
        default=[],
        help="Feature override like qwen=true or vieneu=false",
    )

    subparsers.add_parser("device-id", help="Print this machine's device id")

    args = parser.parse_args()
    if args.command == "init-keys":
        create_keys(Path(args.private_key), Path(args.public_key))
    elif args.command == "issue":
        issue_license(args)
    elif args.command == "device-id":
        print(current_device_id())


def create_keys(private_key_path: Path, public_key_path: Path) -> None:
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    if private_key_path.exists():
        raise SystemExit(f"Private key already exists: {private_key_path}")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Private key: {private_key_path}")
    print(f"Public key:  {public_key_path}")


def issue_license(args) -> None:
    expires_at = _validate_expiry(args.expires_at)
    features = dict(DEFAULT_FEATURES)
    features.update(_parse_feature_flags(args.feature))
    payload = {
        "email": args.email,
        "expires_at": expires_at,
        "plan": args.plan,
        "device_id": args.device_id,
        "features": features,
    }
    private_key_pem = Path(args.private_key).read_bytes()
    payload["signature"] = sign_payload(private_key_pem, payload)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created license: {output}")


def _validate_expiry(value: str) -> str:
    normalized = value.strip().replace(" ", "T")
    try:
        if "T" in normalized:
            datetime.fromisoformat(normalized)
            return normalized
        datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit("--expires-at must use YYYY-MM-DD or YYYY-MM-DDTHH:MM") from exc
    return value


def _parse_feature_flags(values: list[str]) -> dict[str, bool]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("--feature must look like name=true or name=false")
        key, raw = value.split("=", 1)
        normalized = raw.strip().lower()
        if normalized not in {"true", "false"}:
            raise SystemExit("--feature value must be true or false")
        parsed[key.strip()] = normalized == "true"
    return parsed


if __name__ == "__main__":
    main()
