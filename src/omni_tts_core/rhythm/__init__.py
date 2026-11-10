"""Nhịp đọc: one pause setting set, applied according to each model's abilities.

The user's values never depend on the model. A capability profile says how a
provider/model can realise each pause layer, and the resolver picks exactly one
owner per layer (model token, library parameter, app split or app stretch) so
nothing is applied twice. Frontends and MCP only display the resolved plan.
"""

from omni_tts_core.rhythm.capabilities import (
    LayerCapability,
    PauseProfile,
    RhythmSwitch,
    pause_profile_for,
)
from omni_tts_core.rhythm.layers import LAYER_GROUPS, LAYERS, LayerSpec, layer_range
from omni_tts_core.rhythm.resolver import (
    LayerResolution,
    RhythmContext,
    RhythmPlan,
    context_for_model,
    diff_rhythm_plans,
    resolve_rhythm_plan,
)

__all__ = [
    "LAYERS",
    "LAYER_GROUPS",
    "LayerCapability",
    "LayerResolution",
    "LayerSpec",
    "PauseProfile",
    "RhythmContext",
    "RhythmPlan",
    "RhythmSwitch",
    "context_for_model",
    "diff_rhythm_plans",
    "layer_range",
    "pause_profile_for",
    "resolve_rhythm_plan",
]
