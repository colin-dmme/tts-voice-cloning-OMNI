"""Compatibility alias for colin_remote_compute.inference."""
import sys
from colin_remote_compute import inference as _implementation
sys.modules[__name__] = _implementation
