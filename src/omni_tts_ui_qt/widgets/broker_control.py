"""Compatibility alias for colin_colab_remote.ui.broker_control."""

import sys
from colin_colab_remote.ui import broker_control as _implementation

sys.modules[__name__] = _implementation
