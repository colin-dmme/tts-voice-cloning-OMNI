"""Compatibility alias for colin_remote_compute.broker.failover."""
import sys
from colin_remote_compute.broker import failover as _implementation
sys.modules[__name__] = _implementation
