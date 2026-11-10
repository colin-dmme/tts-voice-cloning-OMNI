"""Compatibility alias for colin_remote_compute.broker.client."""
import sys
from colin_remote_compute.broker import client as _implementation
sys.modules[__name__] = _implementation
