"""Narrative pacing: tiered pauses and cross-faded music bridges for long narration."""

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.existing_output_repacer import (
    chapter_lines,
    remapped_timings,
    repace_existing_output,
)
from omni_tts_core.narrative_pacing.pacing_renderer import (
    PacingResult,
    apply_narrative_pacing,
)

__all__ = [
    "PacingResult",
    "PacingUnit",
    "apply_narrative_pacing",
    "chapter_lines",
    "remapped_timings",
    "repace_existing_output",
]
