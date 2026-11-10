"""Small silence clean-up used when a model's own silence removal is turned off."""

from __future__ import annotations

import numpy as np

_HOP_SECONDS = 0.005


def trim_edges(
    audio: np.ndarray,
    sample_rate: int,
    *,
    lead: bool,
    tail: bool,
    threshold_db: float = -45.0,
    keep_seconds: float = 0.02,
) -> np.ndarray:
    """Drop the silence at a fragment's joined edges (Nhịp đọc split seams).

    With the edges gone, the pause inserted at the seam is the total pause
    heard instead of being added to the silence each fragment carries.
    """
    wave = np.asarray(audio, dtype=np.float32)
    if wave.ndim != 1 or not (lead or tail):
        return audio
    hop = max(1, int(round(_HOP_SECONDS * sample_rate)))
    usable = wave.size // hop * hop
    if not usable:
        return audio
    level = 20 * np.log10(np.sqrt(np.mean(wave[:usable].astype(np.float64).reshape(-1, hop) ** 2, axis=1)) + 1e-9)
    loud = np.flatnonzero(level >= threshold_db)
    if not loud.size:
        return audio
    keep = int(keep_seconds * sample_rate)
    start = max(0, loud[0] * hop - keep) if lead else 0
    end = min(wave.size, (loud[-1] + 1) * hop + keep) if tail else wave.size
    return wave[start:end]


def tidy_silences(
    audio: np.ndarray,
    sample_rate: int,
    *,
    threshold_db: float = -50.0,
    edge_keep_seconds: float = 0.1,
    long_seconds: float = 1.5,
    shorten_to_seconds: float = 0.9,
) -> np.ndarray:
    """Trim edge silence and shorten abnormal inner silences.

    Normal pauses (anything up to ``long_seconds``) are kept exactly, so the
    pacing pass sees the model's real rhythm; only stalls longer than that are
    cut to ``shorten_to_seconds`` around their centre. A chunk never spans a
    paragraph boundary, so no intended pause inside it is that long.
    """
    wave = np.asarray(audio, dtype=np.float32)
    flat = wave.reshape(-1) if wave.ndim > 1 and min(wave.shape) == 1 else wave
    if flat.ndim != 1 or flat.size == 0:
        return audio
    hop = max(1, int(round(_HOP_SECONDS * sample_rate)))
    frames = flat[: flat.size // hop * hop].reshape(-1, hop)
    if not len(frames):
        return audio
    level = 20 * np.log10(np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-9)
    loud = np.flatnonzero(level >= threshold_db)
    if not loud.size:
        return audio
    keep = int(round(edge_keep_seconds * sample_rate))
    start = max(0, loud[0] * hop - keep)
    end = min(flat.size, (loud[-1] + 1) * hop + keep)
    quiet = level < threshold_db
    pieces, cursor = [], start
    edges = np.diff(np.concatenate([[0], quiet.astype(np.int8), [0]]))
    long_frames = long_seconds / _HOP_SECONDS
    target = int(round(shorten_to_seconds * sample_rate))
    for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        if b - a <= long_frames:
            continue
        s0, s1 = a * hop, b * hop
        if s0 <= start or s1 >= end:
            continue
        # Keep target samples of the stall: half from each side.
        cut0, cut1 = s0 + target // 2, s1 - (target - target // 2)
        pieces.append(flat[cursor:cut0])
        cursor = cut1
    pieces.append(flat[cursor:end])
    result = np.concatenate(pieces) if len(pieces) > 1 else flat[start:end]
    return result.reshape(1, -1) if wave.ndim > 1 else result
