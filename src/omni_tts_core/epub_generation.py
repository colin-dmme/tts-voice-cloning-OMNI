"""Chapter-sized generation through the existing TTS pipeline and SRT clock."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from threading import Event

import soundfile as sf
from filelock import FileLock, Timeout

from omni_tts_core.progress import ProgressEvent, check_cancel, emit_progress
from omni_tts_core.subtitles.srt_builder import write_srt
from omni_tts_core.text.epub_reader import read_epub
from omni_tts_core.text.source_reader import SourceUnit
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import GenerateSpeechResult, SegmentTiming


def chapter_units(
    chapter, options, *, read_volume: bool, has_next: bool
) -> list[SourceUnit]:
    units = []

    def add(text, pause=None, kind=""):
        units.append(SourceUnit(len(units) + 1, text, pause, kind))

    if read_volume and chapter.volume:
        add(chapter.volume, options.volume_pause_ms, "volume")
    if options.read_titles:
        add(chapter.title, options.title_pause_ms, "title")
    for block in chapter.blocks:
        if block.role == "scene":
            if units:
                # This replaces the paragraph boundary; it is never added twice.
                units[-1] = replace(units[-1], pause_after_ms=options.scene_pause_ms, pause_kind="scene")
        elif block.text.strip():
            add(block.text)
    if units:
        units[-1] = replace(
            units[-1], pause_after_ms=options.chapter_pause_ms if has_next else 0, pause_kind="chapter"
        )
    return units


def _atomic_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _publish(wav: Path, target: Path, bitrate: int, cancel_event=None):
    """Encode from PCM once; keep the destination private until complete."""
    handle, raw = tempfile.mkstemp(
        prefix=".epub-", suffix=target.suffix, dir=target.parent
    )
    os.close(handle)
    tmp = Path(raw)
    try:
        check_cancel(cancel_event)
        if target.suffix == ".wav":
            shutil.copyfile(wav, tmp)
        else:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ConfigError("Xuất EPUB thành MP3 cần ffmpeg trong PATH.")
            with tempfile.TemporaryFile() as log:
                process = subprocess.Popen(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(wav),
                        "-map_metadata",
                        "-1",
                        "-ac",
                        "1",
                        "-ar",
                        "44100",
                        "-codec:a",
                        "libmp3lame",
                        "-b:a",
                        f"{bitrate}k",
                        str(tmp),
                    ],
                    stdout=log,
                    stderr=log,
                )
                try:
                    while True:
                        check_cancel(cancel_event)
                        try:
                            process.wait(timeout=0.2)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                if process.returncode:
                    log.seek(0)
                    raise ConfigError(
                        "Lỗi xuất MP3: "
                        + log.read().decode("utf-8", errors="replace")[-500:]
                    )
        check_cancel(cancel_event)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def _read_timings(path, offset):
    def seconds(stamp):
        h, m, s, ms = map(int, re.split(r"[:,]", stamp))
        return h * 3600 + m * 60 + s + ms / 1000

    result = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        if len(lines) >= 3 and " --> " in lines[1]:
            start, end = lines[1].split(" --> ")
            result.append(
                SegmentTiming(
                    index=0,
                    text="\n".join(lines[2:]),
                    start_seconds=offset + seconds(start),
                    end_seconds=offset + seconds(end),
                )
            )
    return result


def _merge(parts, output_dir, stem, request, progress_callback, cancel_event):
    from omni_tts_core.service import _available_output_pair

    target, subtitle = _available_output_pair(
        output_dir, stem, False, request.output_srt, request.output_audio_format
    )
    raw = output_dir / f".merged-{request.model_id}-{os.getpid()}.wav"
    timings, offset, rate = [], 0.0, None
    try:
        writer = None
        try:
            for i, part in enumerate(parts):
                check_cancel(cancel_event)
                with sf.SoundFile(str(part.audio_path)) as reader:
                    if writer is None:
                        rate = reader.samplerate
                        # RF64 permits books longer than the 4 GB RIFF limit.
                        writer = sf.SoundFile(
                            str(raw),
                            mode="w",
                            samplerate=rate,
                            channels=1,
                            subtype="PCM_16",
                            format="RF64",
                        )
                    if reader.samplerate != rate or reader.channels != 1:
                        raise ConfigError(
                            "Audio các chương có sample rate hoặc số kênh không khớp."
                        )
                    if part.srt_path:
                        timings.extend(_read_timings(part.srt_path, offset))
                    for chunk in reader.blocks(blocksize=65536, dtype="float32"):
                        check_cancel(cancel_event)
                        writer.write(chunk)
                    offset += reader.frames / rate
                emit_progress(
                    progress_callback,
                    f"Đang ghép chương {i + 1}/{len(parts)}",
                    i + 1,
                    len(parts),
                )
        finally:
            if writer:
                writer.close()
        _publish(raw, target, request.mp3_bitrate_kbps, cancel_event)
        if subtitle:
            write_srt(
                subtitle,
                [s.model_copy(update={"index": i + 1}) for i, s in enumerate(timings)],
            )
        return target, subtitle
    finally:
        raw.unlink(missing_ok=True)


def generate_epub(
    service,
    source: Path,
    template,
    output_dir=None,
    progress_callback=None,
    cancel_event: Event | None = None,
):
    from omni_tts_core.service import _available_output_pair, _safe_stem

    book = read_epub(source)
    options = template.epub_options
    chapters = book.select(options)
    # Freeze the real profile/reference and pronunciation before making a cache key.
    request = service.freeze_pronunciation(service._apply_voice_profile(template))
    base = _safe_stem(request.output_stem or source.stem)
    destination = (output_dir or request.output_dir or source.parent) / f"{base}-audio"
    destination.mkdir(parents=True, exist_ok=True)
    job_id, job_dir = service.job_store.create_job_dir()
    payload = request.model_dump(mode="json")
    payload["source_hash"] = hashlib.sha256(source.read_bytes()).hexdigest()
    if options.music.enabled:
        from omni_tts_core.chapter_music import ChapterMusicRenderer
        payload["music_asset_sha256"] = ChapterMusicRenderer(options.music).fingerprint()
    if request.reference_audio_path and request.reference_audio_path.is_file():
        payload["reference_hash"] = hashlib.sha256(
            request.reference_audio_path.read_bytes()
        ).hexdigest()
    signature = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    cache = destination / ".colin-epub" / signature
    cache.mkdir(parents=True, exist_ok=True)
    checkpoint = cache / "completed.json"
    lock = FileLock(str(destination / ".epub.lock"))
    while True:
        check_cancel(cancel_event)
        try:
            lock.acquire(timeout=0.2)
            break
        except Timeout:
            emit_progress(
                progress_callback, "Đang chờ tác vụ EPUB dùng cùng thư mục…", 0, 1
            )
    try:
        try:
            completed = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            completed = {}
        parts, published, last_volume = [], [], None
        for index, chapter in enumerate(chapters):
            check_cancel(cancel_event)
            key = str(chapter.index)
            previous = completed.get(key)
            part = (
                GenerateSpeechResult.model_validate(previous["raw"])
                if previous
                else None
            )
            if part and not (
                part.audio_path.is_file()
                and (
                    not request.output_srt
                    or (part.srt_path and part.srt_path.is_file())
                )
            ):
                part = None
            if part is None:
                units = chapter_units(
                    chapter,
                    options,
                    read_volume=options.include_volumes
                    and chapter.volume != last_volume,
                    has_next=index < len(chapters) - 1,
                )
                chapter_request = request.model_copy(
                    update={
                        "text": "\n\n".join(u.text for u in units),
                        "source_path": source,
                        "output_dir": cache,
                        "output_stem": f"{chapter.index:04d}",
                        "output_mode": "merged",
                        "output_audio_format": "wav",
                        "append_stem_suffix": False,
                        "overwrite": False,
                    }
                )

                def progress(event, index=index, title=chapter.title):
                    if progress_callback:
                        progress_callback(
                            ProgressEvent(
                                message=f"{title}: {event.message}",
                                current=(index * 1000 + int(event.percent * 10)) * 0.9,
                                total=len(chapters) * 1000,
                            )
                        )

                part = service.generate_audio(
                    chapter_request, progress, cancel_event, source_units=units
                )
                completed[key] = {"raw": part.model_dump(mode="json")}
                _atomic_json(checkpoint, completed)
            else:
                emit_progress(
                    progress_callback,
                    f"Dùng lại chương đã hoàn tất: {chapter.title}",
                    (index + 1) * 0.9,
                    len(chapters),
                )
            last_volume = chapter.volume
            parts.append(part)
            if options.output_mode == "chapters":
                entry = completed[key]
                audio = Path(entry.get("audio", ""))
                sub = Path(entry["srt"]) if entry.get("srt") else None
                if not audio.is_file() or (
                    request.output_srt and (sub is None or not sub.is_file())
                ):
                    audio, sub = _available_output_pair(
                        destination,
                        _safe_stem(f"{chapter.index:04d}-{chapter.title}"),
                        False,
                        request.output_srt,
                        request.output_audio_format,
                    )
                    _publish(
                        part.audio_path, audio, request.mp3_bitrate_kbps, cancel_event
                    )
                    if sub:
                        shutil.copyfile(part.srt_path, sub)
                    entry.update(audio=str(audio), srt=str(sub) if sub else None)
                    _atomic_json(checkpoint, completed)
                published.append((audio, sub))
        check_cancel(cancel_event)
        if options.output_mode == "merged":

            def merge_progress(event):
                emit_progress(
                    progress_callback, event.message, 90 + event.percent * 0.08, 100
                )

            emit_progress(
                progress_callback, "Đang ghép audio và phụ đề của sách…", 90, 100
            )
            published = [
                _merge(parts, destination, base, request, merge_progress, cancel_event)
            ]
        result = GenerateSpeechResult(
            job_id=job_id,
            job_dir=job_dir,
            audio_path=published[0][0],
            srt_path=published[0][1],
            item_audio_paths=[p[0] for p in published],
            item_srt_paths=[p[1] for p in published if p[1]],
            segment_count=sum(p.segment_count for p in parts),
            duration_seconds=sum(p.duration_seconds for p in parts),
            message=f"Đã tạo {len(chapters)} chương EPUB; khoảng nghỉ và SRT dùng cùng timeline.",
            pronunciation_report_path=parts[0].pronunciation_report_path,
            pronunciation_snapshot_hash=parts[0].pronunciation_snapshot_hash,
            pronunciation_preset_ids=parts[0].pronunciation_preset_ids,
            pronunciation_term_count=sum(p.pronunciation_term_count for p in parts),
            pronunciation_match_count=sum(p.pronunciation_match_count for p in parts),
            pronunciation_conflict_count=sum(
                p.pronunciation_conflict_count for p in parts
            ),
        )
        service.job_store.save_json(
            job_dir / "epub-preview.json", book.preview(options, limit=500)
        )
        service.job_store.save_json(job_dir / "result.json", result)
        emit_progress(progress_callback, result.message, 1, 1)
        return result
    finally:
        lock.release()
