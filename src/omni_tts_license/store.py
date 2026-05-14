from __future__ import annotations

import os
import shutil
from pathlib import Path

from omni_tts_license.errors import LicenseInstallError


APP_DIR_NAME = "OmniTTS"
LICENSE_FILE_NAME = "license.json"


def license_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_DIR_NAME
    return Path.home() / ".omni_tts"


def license_path() -> Path:
    return license_dir() / LICENSE_FILE_NAME


def install_license(source_path: str | Path) -> Path:
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise LicenseInstallError("Không tìm thấy file license.")
    destination = license_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination
