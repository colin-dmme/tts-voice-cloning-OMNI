"""Incremental batch progress for engines that write one WAV per chunk.

Workers write each chunk file as soon as it is done, so the app can report real
progress while synthesis is still running instead of waiting for the worker to
finish and then reporting everything at once.

Engines driven by ``run_worker_process`` pass ``report`` as its ``tick_callback``;
persistent stdin/stdout workers call it from their own wait loop.
"""

from __future__ import annotations

import time
from pathlib import Path

import soundfile as sf

from omni_tts_core.engines.base import BatchChunkCallback, BatchProgressCallback


def audio_file_ready(path: Path, minimum_age_seconds: float = 0.2) -> bool:
    """True when the WAV exists, stopped changing, and holds real audio."""
    if not path.exists():
        return False
    try:
        if time.time() - path.stat().st_mtime < minimum_age_seconds:
            return False
        return sf.info(str(path)).frames > 0
    except Exception:
        return False


def report_ready_chunks(
    chunks: list[dict],
    reported_chunks: set[int],
    progress_callback: BatchProgressCallback | None,
    chunk_callback: BatchChunkCallback | None,
    *,
    force: bool = False,
) -> None:
    """Report every chunk finished since the last call.

    ``force`` skips the readiness check; use it for the final sweep once the
    worker has confirmed success, so the last chunk never stays unreported
    because its file was written a fraction of a second ago.
    """
    before = len(reported_chunks)
    for index, chunk in enumerate(chunks):
        if index in reported_chunks:
            continue
        out = Path(chunk["output_path"])
        if not force and not audio_file_ready(out):
            continue
        if force and not out.exists():
            continue
        reported_chunks.add(index)
        if chunk_callback is not None:
            chunk_callback(index, out)
    if progress_callback is not None and len(reported_chunks) != before:
        progress_callback(len(reported_chunks), len(chunks))
