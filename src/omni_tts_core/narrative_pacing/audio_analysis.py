"""Frame-level silence map shared by the pacing steps."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HOP_SECONDS = 0.005
QUIET_DB = -50.0


@dataclass(frozen=True)
class PacingUnit:
    """One paragraph (or SRT cue) on the source timeline, in seconds."""

    start: float
    end: float
    text: str
    # The boundary after this unit belongs to someone else (EPUB title,
    # chapter, scene): pacing leaves it exactly as it is.
    locked_after: bool = False


class SilenceMap:
    """RMS per 5 ms frame, computed once for the whole narration."""

    def __init__(self, audio: np.ndarray, sample_rate: int):
        self.sample_rate = sample_rate
        hop = max(1, int(round(HOP_SECONDS * sample_rate)))
        self.hop = hop
        n = len(audio) // hop
        frames = np.asarray(audio[: n * hop], dtype=np.float32).reshape(n, hop)
        rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
        self.frame_db = 20 * np.log10(rms + 1e-9)

    def quiet_runs(
        self, start: float, end: float, min_seconds: float = 0.08
    ) -> list[tuple[float, float]]:
        """Silent spans (start, end) inside [start, end] at least min_seconds long."""
        step = self.hop / self.sample_rate
        i0 = max(0, int(start / step))
        i1 = min(len(self.frame_db), int(end / step))
        if i1 <= i0:
            return []
        quiet = (self.frame_db[i0:i1] < QUIET_DB).astype(np.int8)
        edges = np.diff(np.concatenate([[0], quiet, [0]]))
        starts = np.flatnonzero(edges == 1)
        ends = np.flatnonzero(edges == -1)
        min_frames = max(1, int(round(min_seconds / step)))
        return [
            ((i0 + a) * step, (i0 + b) * step)
            for a, b in zip(starts, ends)
            if b - a >= min_frames
        ]

    def boundary_gap(self, prev_end: float, next_start: float) -> tuple[float, float]:
        """Longest silence around a paragraph boundary; falls back to the nominal gap."""
        runs = self.quiet_runs(prev_end - 0.4, next_start + 0.4, min_seconds=0.05)
        if not runs:
            return prev_end, max(prev_end, next_start)
        return max(runs, key=lambda r: r[1] - r[0])

    def speech_level_db(self) -> float:
        """Mean energy of active speech frames (rough loudness reference)."""
        active = self.frame_db[self.frame_db > -45.0]
        if not active.size:
            return -20.0
        power = np.mean(10 ** (active / 10))
        return float(10 * np.log10(power))


def active_level_db(audio: np.ndarray, sample_rate: int) -> float:
    return SilenceMap(audio, sample_rate).speech_level_db()
