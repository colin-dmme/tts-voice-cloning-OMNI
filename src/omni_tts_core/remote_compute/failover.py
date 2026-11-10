"""Compatibility alias for colin_colab_remote.broker.failover."""

import sys
from colin_colab_remote.broker import failover as _implementation

sys.modules[__name__] = _implementation
