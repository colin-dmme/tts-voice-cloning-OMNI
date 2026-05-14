from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    code: str
    message: str
    email: str | None = None
    plan: str | None = None
    expires_at: datetime | None = None
    device_id: str | None = None
    features: dict[str, bool] = field(default_factory=dict)
    license_path: Path | None = None

    def feature_enabled(self, feature: str) -> bool:
        return self.valid and self.features.get(feature, True)


LicenseData = dict[str, Any]
