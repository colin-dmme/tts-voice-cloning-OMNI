"""Pluggable license providers for Colin TTS Local."""

from omni_tts_license.local_signed import LocalSignedLicenseProvider
from omni_tts_license.models import LicenseStatus

__all__ = ["LicenseStatus", "LocalSignedLicenseProvider"]
