from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def concatenate_segments(
    segments: list[np.ndarray],
    sample_rate: int,
    pause_ms: int,
) -> np.ndarray:
    if not segments:
        return np.array([], dtype=np.float32)
    pause_samples = int(sample_rate * pause_ms / 1000)
    pause = np.zeros(pause_samples, dtype=np.float32)
    pieces: list[np.ndarray] = []
    for index, segment in enumerate(segments):
        pieces.append(_to_mono_float32(segment))
        if index < len(segments) - 1 and pause_samples > 0:
            pieces.append(pause)
    return np.concatenate(pieces)


def save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), _to_mono_float32(audio), sample_rate)


def duration_seconds(audio: np.ndarray, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(audio) / sample_rate)


def _to_mono_float32(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio)
    if array.ndim == 2 and array.shape[0] <= 8 and array.shape[0] < array.shape[1]:
        array = array.mean(axis=0)
    elif array.ndim == 2:
        array = array.mean(axis=1)
    return array.astype(np.float32, copy=False)
