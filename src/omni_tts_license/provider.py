from __future__ import annotations

from pathlib import Path
from typing import Protocol

from omni_tts_license.models import LicenseStatus


class LicenseProvider(Protocol):
    def get_status(self) -> LicenseStatus:
        ...

    def install_license(self, source_path: str | Path) -> LicenseStatus:
        ...

    def current_device_id(self) -> str:
        ...

    def is_feature_enabled(self, feature: str) -> bool:
        ...
