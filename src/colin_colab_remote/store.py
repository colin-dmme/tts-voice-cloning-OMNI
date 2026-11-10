"""Compatibility alias for colin_remote_compute.store."""
import sys
from colin_remote_compute import store as _implementation
sys.modules[__name__] = _implementation
