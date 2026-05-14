from __future__ import annotations

import hashlib
import os
import platform
import subprocess


def current_device_id() -> str:
    raw = _windows_machine_guid() or _fallback_fingerprint()
    digest = hashlib.sha256(f"omni-tts-local:{raw}".encode("utf-8")).hexdigest()
    return digest[:24].upper()


def _windows_machine_guid() -> str | None:
    if platform.system().lower() != "windows":
        return None
    try:
        completed = subprocess.run(
            [
                "reg",
                "query",
                r"HKLM\SOFTWARE\Microsoft\Cryptography",
                "/v",
                "MachineGuid",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    for line in completed.stdout.splitlines():
        if "MachineGuid" in line:
            parts = line.split()
            if parts:
                return parts[-1].strip()
    return None


def _fallback_fingerprint() -> str:
    return "|".join(
        [
            platform.node(),
            platform.system(),
            platform.release(),
            os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERDOMAIN", ""),
        ]
    )
