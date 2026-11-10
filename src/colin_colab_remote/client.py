"""Compatibility alias for colin_remote_compute.client."""
import sys
from colin_remote_compute import client as _implementation
sys.modules[__name__] = _implementation
