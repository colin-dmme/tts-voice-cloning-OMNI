"""Lengthen sentence-final pauses inside a paragraph.

TTS engines often give a full stop the same 0.2-0.3 s as a comma. Punctuation
marks are aligned to the real silences with a monotonic DP on expected time
(characters are spoken at a roughly constant rate), then only the silences
matched to . ? ! : ; … are stretched to their target length; commas only get
a floor so a rushed 0.1 s breath becomes a natural short pause.
"""

from __future__ import annotations

import random
import re

import numpy as np

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit, SilenceMap
from omni_tts_core.rhythm.layers import MARK_LAYERS, has_range, sample_ms
from omni_tts_shared.narrative_pacing import NarrativePacingOptions

_MARKS = re.compile(r"[,.?!:;…—](?=\s)")
_SKIP_MARK, _SKIP_RUN, _TOLERANCE = 0.55, 0.45, 1.3
_SENTENCE_END = frozenset(".?!…？")
SHORT_SENTENCE_CHARS = 32
# Silence runs (s): all runs from _ALIGN_RUN drive the speech clock; a mark is
# stretched only from _MARK_RUN (commas from _COMMA_RUN).
_ALIGN_RUN, _MARK_RUN, _COMMA_RUN = 0.05, 0.07, 0.08


def _targets(options: NarrativePacingOptions) -> dict[str, float]:
    full = options.sentence_end_pause_ms / 1000
    return {
        ".": full, "!": full, "…": full + 0.03,
        "?": options.question_end_pause_ms / 1000, "？": options.question_end_pause_ms / 1000,
        ":": options.colon_pause_ms / 1000, ";": options.colon_pause_ms / 1000,
        **({",": options.comma_min_pause_ms / 1000} if options.comma_min_pause_ms else {}),
    }


def _short_sentence_marks(text: str, marks: list[tuple[int, str]]) -> set[int]:
    """Sentence-final marks next to a short sentence (before or after it)."""
    ends = [i for i, (_, mark) in enumerate(marks) if mark in _SENTENCE_END]
    bounds = [-1] + [marks[i][0] for i in ends] + [len(text)]
    lengths = [bounds[k + 1] - bounds[k] for k in range(len(bounds) - 1)]
    # Mark ends[k] closes sentence k and opens sentence k + 1.
    return {
        i for k, i in enumerate(ends)
        if min(lengths[k], lengths[k + 1]) <= SHORT_SENTENCE_CHARS
    }


def _align(expected: list[float], centers: list[float]) -> list[tuple[int, int]]:
    """Monotonic matching of marks to silences; returns (mark_index, run_index)."""
    m_count, r_count = len(expected), len(centers)
    cost = np.full((m_count + 1, r_count + 1), np.inf)
    cost[0, :] = np.arange(r_count + 1) * _SKIP_RUN
    cost[:, 0] = np.arange(m_count + 1) * _SKIP_MARK
    move = np.zeros((m_count + 1, r_count + 1), dtype=np.int8)
    for m in range(1, m_count + 1):
        for r in range(1, r_count + 1):
            d = abs(expected[m - 1] - centers[r - 1])
            options = (
                cost[m - 1, r - 1] + (d if d < _TOLERANCE else np.inf),
                cost[m - 1, r] + _SKIP_MARK,
                cost[m, r - 1] + _SKIP_RUN,
            )
            move[m, r] = int(np.argmin(options))
            cost[m, r] = options[move[m, r]]
    pairs, m, r = [], m_count, r_count
    while m > 0 and r > 0:
        if move[m, r] == 0:
            pairs.append((m - 1, r - 1))
            m, r = m - 1, r - 1
        elif move[m, r] == 1:
            m -= 1
        else:
            r -= 1
    return pairs[::-1]


def plan_sentence_pauses(
    silence: SilenceMap,
    unit: PacingUnit,
    options: NarrativePacingOptions,
    rng: random.Random,
    skip_layers: frozenset[str] = frozenset(),
) -> list[tuple[float, float]]:
    """(time_in_source, extra_seconds) for each sentence-final pause to stretch.

    ``skip_layers`` are pause layers another owner already realises (app
    punctuation split, a library parameter, model tokens); they are left alone.
    """
    text = " ".join(unit.text.split())
    # The paragraph's final mark belongs to the paragraph boundary, paced separately.
    marks = [(m.start(), m.group(0)) for m in _MARKS.finditer(text + " ") if m.start() < len(text) - 1]
    duration = unit.end - unit.start
    if not marks or duration <= 0.6 or not text:
        return []
    runs = silence.quiet_runs(unit.start + 0.2, unit.end - 0.2, min_seconds=_ALIGN_RUN)
    if not runs:
        return []
    # Align on a speech-only clock: characters map to spoken time, so the
    # model's own long pauses earlier in the paragraph do not push later marks
    # out of place (measured 2026-11-10: absolute time missed ~1/3 of marks).
    speech = duration - sum(b - a for a, b in runs)
    expected = [speech * pos / len(text) for pos, _ in marks]
    clock, before = [], 0.0
    for a, b in runs:
        clock.append(a - unit.start - before)
        before += b - a
    centers = [(a + b) / 2 for a, b in runs]
    targets = _targets(options)
    short = _short_sentence_marks(text, marks)
    inserts = []
    for mark_index, run_index in _align(expected, clock):
        mark = marks[mark_index][1]
        # Short dips are trusted only at sentence-level marks; commas need a
        # clear breath so a pause is never opened inside a word.
        if runs[run_index][1] - runs[run_index][0] < (_COMMA_RUN if mark == "," else _MARK_RUN):
            continue
        layer = MARK_LAYERS.get(mark)
        ranged = layer is not None and has_range(options, layer)
        if layer is None or layer in skip_layers:
            target = None
        elif ranged:
            target = sample_ms(options, layer, rng) / 1000
        else:
            target = targets.get(mark)
        if mark_index in short and "short_sentence" not in skip_layers:
            ranged = ranged or has_range(options, "short_sentence")
            target = max(target or 0.0, sample_ms(options, "short_sentence", rng) / 1000)
        if target is None:
            continue
        current = runs[run_index][1] - runs[run_index][0]
        # Commas are a floor only (no jitter); sentence marks get a little
        # variation unless the user gave a Min–Max range.
        jitter = 0.0 if mark == "," or ranged else rng.uniform(-0.04, 0.05)
        extra = target + jitter - current
        if extra > 0.04:
            inserts.append((centers[run_index], extra))
    return inserts
