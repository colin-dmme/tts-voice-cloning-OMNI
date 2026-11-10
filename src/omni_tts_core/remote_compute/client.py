"""Compatibility alias for colin_colab_remote.broker.client."""

import sys
from colin_colab_remote.broker import client as _implementation

sys.modules[__name__] = _implementation
