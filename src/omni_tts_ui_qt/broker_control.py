"""Compatibility alias for colin_colab_remote.ui.broker_app."""

import sys
from colin_colab_remote.ui import broker_app as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
