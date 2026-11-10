"""Hook used by TtsService after a merged text job has been assembled."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit, SilenceMap
from omni_tts_core.narrative_pacing.existing_output_repacer import chapter_lines
from omni_tts_core.narrative_pacing.pacing_renderer import apply_narrative_pacing
from omni_tts_core.narrative_pacing.sentence_pause_aligner import plan_sentence_pauses
from omni_tts_shared.narrative_pacing import NarrativePacingOptions
from omni_tts_shared.schemas import GenerateSpeechRequest, SegmentTiming

if TYPE_CHECKING:
    from omni_tts_core.rhythm.execution import RhythmExecution


def pace_merged_output(
    combined: np.ndarray,
    sample_rate: int,
    units: list[PacingUnit],
    timings: list[SegmentTiming],
    request: GenerateSpeechRequest,
    job_dir: Path,
    *,
    rhythm: RhythmExecution | None = None,
) -> tuple[np.ndarray, list[SegmentTiming], Path]:
    """Return paced audio, SRT timings on the new timeline and the report path."""
    options = rhythm.pacing_options if rhythm is not None else request.narrative_pacing
    result = apply_narrative_pacing(
        combined, sample_rate, units, options,
        language=request.language, context=request.text[:2000],
        skip_layers=rhythm.skip_layers if rhythm is not None else frozenset(),
    )
    paced_timings = [
        t.model_copy(update={
            "start_seconds": result.remap(t.start_seconds),
            "end_seconds": result.remap(t.end_seconds),
        })
        for t in timings
    ]
    report = dict(result.report, chapters=chapter_lines(result))
    if rhythm is not None:
        report["rhythm_plan"] = rhythm.report()
    report_path = job_dir / "pacing_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return result.audio, paced_timings, report_path


def unit_window(chunk_windows: list[tuple[float, float]], text: str, *,
                locked_after: bool = False) -> PacingUnit | None:
    if not chunk_windows:
        return None
    return PacingUnit(chunk_windows[0][0], chunk_windows[-1][1], text, locked_after)


def stretch_sentence_pauses(
    audio: np.ndarray,
    sample_rate: int,
    text: str,
    options: NarrativePacingOptions,
    skip_layers: frozenset[str] = frozenset(),
    *,
    seed: int = 0,
) -> np.ndarray:
    """Pace the pauses inside one stand-alone file (split output)."""
    wave = np.asarray(audio, dtype=np.float32)
    if wave.ndim != 1 or not options.sentence_pauses_enabled or not text.strip():
        return audio
    silence = SilenceMap(wave, sample_rate)
    loud = np.flatnonzero(silence.frame_db > -45.0)
    if not loud.size:
        return audio
    step = silence.hop / sample_rate
    unit = PacingUnit(loud[0] * step, (loud[-1] + 1) * step, text)
    inserts = sorted(plan_sentence_pauses(silence, unit, options, random.Random(seed), skip_layers))
    if not inserts:
        return audio
    pieces, pos = [], 0
    for at, extra in inserts:
        cut = int(round(at * sample_rate))
        if cut < pos:
            continue
        pieces += [wave[pos:cut], np.zeros(int(round(extra * sample_rate)), dtype=np.float32)]
        pos = cut
    pieces.append(wave[pos:])
    return np.concatenate(pieces)
