"""Re-pace an audio file that was already generated, using its SRT cues as paragraphs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from omni_tts_core.audio.wav_tools import read_audio_mono, save_audio_atomic
from omni_tts_core.narrative_pacing.audio_analysis import PacingUnit
from omni_tts_core.narrative_pacing.pacing_renderer import (
    PacingResult,
    apply_narrative_pacing,
)
from omni_tts_core.subtitles.srt_builder import write_srt
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.narrative_pacing import NarrativePacingOptions
from omni_tts_shared.schemas import SegmentTiming

_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def _seconds(stamp: str) -> float:
    match = _TIME.search(stamp)
    if not match:
        raise ConfigError(f"Mốc thời gian SRT không hợp lệ: {stamp!r}")
    h, m, s, ms = (int(v) for v in match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


def read_srt_units(path: Path) -> list[PacingUnit]:
    content = path.read_text(encoding="utf-8-sig").replace("\r", "")
    units = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        stamp = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if stamp is None:
            continue
        start, end = lines[stamp].split("-->")
        text = " ".join(lines[stamp + 1:]).strip()
        if text:
            units.append(PacingUnit(_seconds(start), _seconds(end), text))
    if not units:
        raise ConfigError("SRT không có cue nào để xếp nhịp.")
    return units


def remapped_timings(units: list[PacingUnit], result: PacingResult) -> list[SegmentTiming]:
    return [
        SegmentTiming(index=i, text=u.text, start_seconds=result.remap(u.start), end_seconds=result.remap(u.end))
        for i, u in enumerate(units, 1)
    ]


def chapter_lines(result: PacingResult) -> list[str]:
    """YouTube-style chapter list: hook at 0:00, then each music entry."""
    def stamp(t: float) -> str:
        t = int(max(0.0, t))
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"

    lines = ["0:00 Mở đầu"]
    for item in result.report.get("music", []):
        if item["kind"] in ("theme", "bridge"):
            title = re.split(r"(?<=[.?!:])\s", item["text"].strip())[0][:60].rstrip(" ,.:")
            lines.append(f"{stamp(item['music_start_seconds'])} {title}")
    return lines


def repace_existing_output(
    audio_path: Path, srt_path: Path, options: NarrativePacingOptions, *,
    output_dir: Path | None = None, language: str = "vi", mp3_bitrate_kbps: int = 192,
) -> dict:
    audio_path, srt_path = Path(audio_path), Path(srt_path)
    for path in (audio_path, srt_path):
        if not path.is_absolute() or not path.is_file():
            raise ConfigError(f"Cần đường dẫn tuyệt đối tới file có sẵn: {path}")
    units = read_srt_units(srt_path)
    audio, rate = read_audio_mono(audio_path)
    if units[-1].end > len(audio) / rate + 1.0:
        raise ConfigError("SRT dài hơn audio; hãy chọn đúng cặp audio và SRT.")
    result = apply_narrative_pacing(
        audio, rate, units, options.model_copy(update={"enabled": True}),
        language=language, context=str(srt_path.name),
    )
    out_dir = Path(output_dir) if output_dir else audio_path.parent / "paced"
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = "mp3" if audio_path.suffix.lower() == ".mp3" else "wav"
    out_audio = out_dir / f"{audio_path.stem}_paced.{fmt}"
    out_srt = out_dir / f"{srt_path.stem}_paced.srt"
    save_audio_atomic(out_audio, result.audio, rate, fmt, mp3_bitrate_kbps)
    write_srt(out_srt, remapped_timings(units, result))
    chapters = out_dir / "chapters.txt"
    chapters.write_text("\n".join(chapter_lines(result)) + "\n", encoding="utf-8")
    report_path = out_dir / "pacing_report.json"
    report_path.write_text(json.dumps(result.report, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"audio_path": str(out_audio), "srt_path": str(out_srt), "chapters_path": str(chapters),
            "report_path": str(report_path), **{k: result.report[k] for k in ("source_seconds", "paced_seconds")},
            "music": result.report["music"]}
