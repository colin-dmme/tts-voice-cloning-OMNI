"""Pick the section layer: clear silences where the topic changes, between music parts.

Music marks the few big parts; sections mark the movements inside each part
("we have seen X, now Y"). They come from the same topic-shift scores, about
one per ``section_interval_minutes``, kept away from each other and from the
music so a long silence never sits right next to a bridge.
"""

from __future__ import annotations

from dataclasses import dataclass

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.boundary_classifier import resolve_language
from omni_tts_core.narrative_pacing.music_bridge_planner import BridgePlan, plan_bridges
from omni_tts_core.narrative_pacing.topic_shift import topic_shift_scores
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

SECTION_MIN_SCORE = 1.0
MIN_GAP_RATIO = 0.45


def plan_sections(
    units: list[PacingUnit], scores: list[float], options: NarrativePacingOptions,
    reserved: set[int],
) -> list[int]:
    """0-based unit indexes that start a new section (a silence before them)."""
    if not options.sections_enabled or len(units) < 3:
        return []
    if options.section_before_units:
        return [
            n - 1 for n in options.section_before_units
            if 1 <= n - 1 < len(units) and n - 1 not in reserved
        ]
    interval = options.section_interval_minutes * 60
    budget = int((units[-1].end - units[0].start) / interval)
    if budget < 1:
        return []
    min_gap = MIN_GAP_RATIO * interval
    anchors = [units[0].start, units[-1].end] + [units[b].start for b in reserved]
    candidates = sorted(
        (b for b in range(1, len(units)) if b not in reserved and scores[b] >= SECTION_MIN_SCORE),
        key=lambda b: -scores[b],
    )
    chosen: list[int] = []
    for b in candidates:
        if len(chosen) >= budget:
            break
        at = units[b].start
        if all(abs(at - anchor) >= min_gap for anchor in anchors):
            chosen.append(b)
            anchors.append(at)
    return sorted(chosen)


@dataclass
class StructurePlan:
    scores: list[float]
    music: BridgePlan
    sections: list[int]


def plan_structure(units: list[PacingUnit], options: NarrativePacingOptions, language: str) -> StructurePlan:
    """All boundary layers above the paragraph: music parts, then silent sections."""
    language = resolve_language(language, " ".join(u.text for u in units[:40]))
    scores = topic_shift_scores(units, language)
    music = plan_bridges(units, options.music, language, scores)
    reserved = set(music.bridges_before) if options.music.enabled else set()
    if options.music.enabled and music.intro_before is not None:
        reserved.add(music.intro_before)
    return StructurePlan(scores, music, plan_sections(units, scores, options, reserved))
