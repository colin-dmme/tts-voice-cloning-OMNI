"""Compatibility alias for colin_remote_compute.context."""
import sys
from colin_remote_compute import context as _implementation
sys.modules[__name__] = _implementation
