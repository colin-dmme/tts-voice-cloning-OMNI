from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omni_tts_license.local_signed import LocalSignedLicenseProvider


class LicenseModeTest(unittest.TestCase):
    def test_disabled_license_mode_enables_owner_build_without_license_file(self) -> None:
        with patch.dict(os.environ, {"COLIN_TTS_LICENSE_MODE": "disabled"}):
            provider = LocalSignedLicenseProvider(
                public_key_path=Path("missing-public-key.pem"),
                installed_license_path=Path("missing-license.json"),
            )

            status = provider.get_status()

        self.assertTrue(status.valid)
        self.assertEqual(status.code, "disabled")
        self.assertTrue(status.feature_enabled("tts"))
        self.assertTrue(status.feature_enabled("vieneu"))
        self.assertTrue(status.feature_enabled("qwen"))


if __name__ == "__main__":
    unittest.main()
