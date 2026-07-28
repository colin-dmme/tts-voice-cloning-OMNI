"""OS desktop actions for source files and generated results.

Path selection and launch rules live in Core so Qt/Tkinter frontends do not
need to guess whether a path should be opened as a file or as a directory.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Callable

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_shared.errors import OmniTtsError


OpenPath = Callable[[Path], None]
RevealPath = Callable[[Path], None]


class DesktopPathService:
    def __init__(
        self,
        open_path: OpenPath | None = None,
        reveal_path: RevealPath | None = None,
    ) -> None:
        self._open_path = open_path or _open_with_default_app
        self._reveal_path = reveal_path or _reveal_in_file_manager

    def open_source_file(self, source_path: Path) -> Path:
        path = _require_file(source_path, "File nguồn không còn tồn tại")
        self._open_path(path)
        return path

    def open_source_folder(self, source_path: Path) -> Path:
        path = _require_file(source_path, "File nguồn không còn tồn tại")
        self._reveal_path(path)
        return path.parent

    def open_result_folder(self, manifest: FileQueueOutputManifest) -> Path:
        target = _preferred_existing_result(manifest)
        if target is not None:
            if target.is_dir():
                self._open_path(target)
                return target
            self._reveal_path(target)
            return target.parent

        for declared in (
            manifest.preferred_audio_path(),
            manifest.preferred_srt_path(),
        ):
            if declared is not None and Path(declared).parent.is_dir():
                folder = Path(declared).parent.resolve(strict=False)
                self._open_path(folder)
                return folder

        raise OmniTtsError("Không tìm thấy file hoặc thư mục kết quả để mở.")


def _preferred_existing_result(manifest: FileQueueOutputManifest) -> Path | None:
    candidates = (
        manifest.preferred_audio_path(existing_only=True),
        manifest.preferred_srt_path(existing_only=True),
        manifest.job_dir,
        *manifest.split_output_dirs,
    )
    for candidate in candidates:
        if candidate is not None and Path(candidate).exists():
            return Path(candidate).resolve(strict=False)
    return None


def _require_file(path: Path, message: str) -> Path:
    normalized = Path(path).expanduser().resolve(strict=False)
    if not normalized.is_file():
        raise OmniTtsError(f"{message}: {normalized}")
    return normalized


def _open_with_default_app(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)])


def _reveal_in_file_manager(path: Path) -> None:
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", "/select,", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path.parent)])
