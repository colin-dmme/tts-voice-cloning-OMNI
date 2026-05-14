from __future__ import annotations


class LicenseError(Exception):
    """Base class for license-related errors."""


class LicenseInstallError(LicenseError):
    """Raised when a license file cannot be imported or stored."""
