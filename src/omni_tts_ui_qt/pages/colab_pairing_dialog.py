"""Compatibility alias for colin_colab_remote.ui.colab_pairing_dialog."""

import sys
from colin_colab_remote.ui import colab_pairing_dialog as _implementation

sys.modules[__name__] = _implementation
