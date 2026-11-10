"""Compatibility alias for colin_colab_remote.broker.local_broker."""

import sys
from colin_colab_remote.broker import local_broker as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
