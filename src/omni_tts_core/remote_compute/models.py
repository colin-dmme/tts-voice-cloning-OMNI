"""Compatibility alias for colin_colab_remote.broker.models."""

import sys
from colin_colab_remote.broker import models as _implementation

sys.modules[__name__] = _implementation
