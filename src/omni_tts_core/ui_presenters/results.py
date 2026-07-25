"""Transform a GenerateSpeechResult into output path collections/manifests.

UI-agnostic; ported from the tkinter app so the file queue and result tools
share identical path handling across GUIs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_shared.schemas import GenerateSpeechResult


def result_output_dirs(results: Iterable[GenerateSpeechResult]) -> list[Path]:
    dirs: list[Path] = []
    seen: set[Path] = set()
    for result in results:
        paths = list(result.item_audio_paths) if result.item_audio_paths else [result.audio_path]
        for path in paths:
            if path is None:
                continue
            folder = Path(path).parent
            if folder not in seen:
                dirs.append(folder)
                seen.add(folder)
    return dirs


def result_output_paths(result: GenerateSpeechResult) -> list[Path]:
    paths: list[Path] = []
    for path in (
        list(result.item_audio_paths)
        + list(result.item_srt_paths)
        + [result.audio_path, result.srt_path]
    ):
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def result_output_manifest(result: GenerateSpeechResult) -> FileQueueOutputManifest:
    split_audio_paths = unique_paths(result.item_audio_paths)
    audio_path = Path(result.audio_path) if result.audio_path else None
    merged_audio_path = (
        audio_path
        if audio_path is not None and audio_path not in split_audio_paths
        else None
    )
    srt_paths = unique_paths([*result.item_srt_paths, result.srt_path])
    return FileQueueOutputManifest(
        split_output_dirs=unique_paths(path.parent for path in split_audio_paths),
        split_audio_paths=split_audio_paths,
        merged_audio_path=merged_audio_path,
        srt_paths=srt_paths,
        job_dir=result.job_dir,
    )


def unique_paths(paths: Iterable[Path | None]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        if value is None:
            continue
        path = Path(value)
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def path_lines(paths: Iterable[Path]) -> str:
    return "\n".join(str(path) for path in paths)
