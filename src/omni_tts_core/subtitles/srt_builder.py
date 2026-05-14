from __future__ import annotations

from pathlib import Path

from omni_tts_shared.schemas import SegmentTiming


def build_srt(segments: list[SegmentTiming]) -> str:
    blocks = []
    for segment in segments:
        start = format_srt_timestamp(segment.start_seconds)
        end = format_srt_timestamp(segment.end_seconds)
        blocks.append(f"{segment.index}\n{start} --> {end}\n{segment.text}")
    return "\n\n".join(blocks) + "\n"


def write_srt(path: Path, segments: list[SegmentTiming]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_srt(segments), encoding="utf-8")


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
