"""Compatibility alias for colin_remote_compute.broker.models."""
import sys
from colin_remote_compute.broker import models as _implementation
sys.modules[__name__] = _implementation
