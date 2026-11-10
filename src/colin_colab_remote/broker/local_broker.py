"""Compatibility alias for colin_remote_compute.broker.local_broker."""
import sys
from colin_remote_compute.broker import local_broker as _implementation
if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
