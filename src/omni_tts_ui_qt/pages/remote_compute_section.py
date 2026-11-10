"""Compatibility alias for colin_colab_remote.ui.remote_compute_section."""

import sys
from colin_colab_remote.ui import remote_compute_section as _implementation

sys.modules[__name__] = _implementation
