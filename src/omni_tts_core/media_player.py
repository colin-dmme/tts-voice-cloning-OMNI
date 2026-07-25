"""Open generated audio in the operating system's default media player.

This module is intentionally UI-toolkit agnostic.  Tkinter, PySide6, or any
future frontend can pass a generation result or queue output manifest here
without owning path-selection or process-launching rules.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

from omni_tts_core.file_queue import FileQueueOutputManifest
from omni_tts_shared.errors import OmniTtsError
from omni_tts_shared.schemas import GenerateSpeechResult

DefaultAppOpener = Callable[[Path], None]


class MediaPlayerService:
    """Select and open generated audio with the OS default application."""

    def __init__(self, opener: DefaultAppOpener | None = None) -> None:
        self._opener = opener or _open_with_default_app

    def play_result(self, result: GenerateSpeechResult) -> Path:
        """Play the preferred audio from a direct text-generation result."""
        return self.play_first_available([result.audio_path, *result.item_audio_paths])

    def play_manifest(self, manifest: FileQueueOutputManifest) -> Path:
        """Play merged queue output when present, otherwise the first split file."""
        return self.play_first_available(
            [manifest.merged_audio_path, *manifest.split_audio_paths]
        )

    def play_first_available(self, candidates: Iterable[Path | str | None]) -> Path:
        """Open the first existing file in ``candidates`` and return its path."""
        supplied = False
        for value in candidates:
            if value is None or not str(value).strip():
                continue
            supplied = True
            path = Path(value).expanduser()
            if not path.is_file():
                continue
            try:
                self._opener(path)
            except OSError as error:
                raise OmniTtsError(
                    f"Windows không thể mở file audio bằng ứng dụng mặc định: {path}"
                ) from error
            return path

        if supplied:
            raise OmniTtsError("Không tìm thấy file audio kết quả để phát.")
        raise OmniTtsError("Kết quả này chưa có file audio để phát.")


def _open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([command, str(path)])
