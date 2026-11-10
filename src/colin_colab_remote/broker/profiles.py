"""Compatibility alias for colin_remote_compute.broker.profiles."""
import sys
from colin_remote_compute.broker import profiles as _implementation
sys.modules[__name__] = _implementation
