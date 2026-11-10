"""Compatibility alias for colin_remote_compute.daemon."""
import sys
from colin_remote_compute import daemon as _implementation
if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
