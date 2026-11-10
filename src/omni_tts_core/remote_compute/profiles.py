"""Compatibility alias for colin_colab_remote.broker.profiles."""

import sys
from colin_colab_remote.broker import profiles as _implementation

sys.modules[__name__] = _implementation
