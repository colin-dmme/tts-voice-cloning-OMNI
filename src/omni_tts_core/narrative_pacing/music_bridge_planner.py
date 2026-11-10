"""Decide where the series theme and the section music bridges go.

Boundary b sits between unit b-1 and unit b (0-based units), i.e. a bridge
"before unit b". The opening hook (unit 0) never gets music.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.boundary_classifier import (
    bridge_strength,
    looks_like_closing,
    looks_like_intro,
    resolve_language,
)
from omni_tts_core.narrative_pacing.topic_shift import topic_shift_scores
from omni_tts_shared.narrative_pacing import NarrativeMusicOptions

INTRO_SEARCH_SECONDS = 180.0
# Boundaries without a marker can still carry music when the vocabulary
# clearly changes and the opening announces a new movement.
UNMARKED_MUSIC_SCORE = 1.1


@dataclass
class BridgePlan:
    intro_before: int | None = None          # 0-based unit index the theme leads into
    bridges_before: list[int] = field(default_factory=list)
    majors_before: list[int] = field(default_factory=list)  # subset of bridges_before: long bridges
    closing: int | None = None                                # bridge before the closing words


def _intro_boundary(units: list[PacingUnit], music: NarrativeMusicOptions, language: str) -> int | None:
    if not music.enabled or not music.theme_track_id or len(units) < 2:
        return None
    if music.intro_before_unit is not None:
        index = music.intro_before_unit - 1
        return index if 1 <= index < len(units) else None
    eligible = [
        i for i in range(1, len(units))
        if units[i].start >= music.hook_min_seconds and units[i].start <= INTRO_SEARCH_SECONDS
    ]
    for i in eligible:
        if looks_like_intro(units[i].text, language):
            return i
    # No explicit series introduction: enter at the first boundary after the hook.
    later = [i for i in range(1, len(units)) if units[i].start >= music.hook_min_seconds]
    return later[0] if later else None


def _closing_boundary(units: list[PacingUnit], language: str) -> int | None:
    tail_from = max(1, int(len(units) * 0.85))
    for i in range(len(units) - 1, tail_from - 1, -1):
        if looks_like_closing(units[i].text, language):
            return i
    return None


def plan_bridges(
    units: list[PacingUnit], music: NarrativeMusicOptions, language: str,
    scores: list[float] | None = None,
) -> BridgePlan:
    language = resolve_language(language, " ".join(u.text for u in units[:40]))
    plan = BridgePlan(intro_before=_intro_boundary(units, music, language))
    if not music.enabled or len(units) < 2:
        return plan
    scores = scores if scores is not None else topic_shift_scores(units, language)
    if music.bridge_before_units or not music.auto_bridges:
        plan.bridges_before = [
            n - 1 for n in music.bridge_before_units
            if 1 <= n - 1 < len(units) and n - 1 != plan.intro_before
        ]
        closing = _closing_boundary(units, language)
        plan.closing = closing if closing in plan.bridges_before else None
        return _with_majors(plan, units, music, scores, closing=plan.closing)

    interval = music.interval_minutes * 60
    total = units[-1].end
    closing = _closing_boundary(units, language)
    stop_at = units[closing].start if closing else total
    last = units[plan.intro_before].start if plan.intro_before else 0.0
    chosen: list[int] = []
    strength = {
        b: bridge_strength(units[b - 1].text, units[b].text, language)
        for b in range(1, len(units))
    }
    while True:
        target = last + interval
        if target > stop_at - 0.4 * interval:
            break
        window = [
            b for b in range(1, len(units))
            if last + 0.6 * interval <= units[b].start <= last + 1.5 * interval
            and units[b].start < stop_at - 0.4 * interval
            and b != plan.intro_before
        ]
        pool = [b for b in window if strength[b] >= 2 or scores[b] >= UNMARKED_MUSIC_SCORE]
        pool = pool or [b for b in window if strength[b] >= 1 and scores[b] >= 0.8]
        pick = None
        if pool:
            # Prefer the clearest change of topic, then closeness to the ideal spacing.
            pick = max(pool, key=lambda b: scores[b] - 0.3 * abs(units[b].start - target) / interval)
        if pick is None:
            last += 0.9 * interval  # nothing suitable: skip ahead, never force music
            continue
        chosen.append(pick)
        last = units[pick].start
    if closing and closing != plan.intro_before:
        chosen.append(closing)
    plan.bridges_before = sorted(set(chosen))
    plan.closing = closing if closing in plan.bridges_before else None
    return _with_majors(plan, units, music, scores, closing)


def _with_majors(
    plan: BridgePlan, units: list[PacingUnit], music: NarrativeMusicOptions,
    scores: list[float], closing: int | None,
) -> BridgePlan:
    """Promote the biggest turns to long bridges: closing + top scores, well spaced."""
    if not music.major_enabled:
        return plan
    if music.major_before_units:
        majors = [n - 1 for n in music.major_before_units if 1 <= n - 1 < len(units) and n - 1 != plan.intro_before]
        plan.bridges_before = sorted(set(plan.bridges_before) | set(majors))
        plan.majors_before = sorted(majors)
        return plan
    interval = music.major_interval_minutes * 60
    budget = round((units[-1].end - units[0].start) / interval) - 1
    majors = [closing] if closing in plan.bridges_before else []
    anchors = [units[b].start for b in majors]
    if plan.intro_before is not None:
        anchors.append(units[plan.intro_before].start)
    for b in sorted(plan.bridges_before, key=lambda b: -scores[b]):
        if budget <= 0:
            break
        if b not in majors and all(abs(units[b].start - a) >= 0.6 * interval for a in anchors):
            majors.append(b)
            anchors.append(units[b].start)
            budget -= 1
    plan.majors_before = sorted(majors)
    return plan
