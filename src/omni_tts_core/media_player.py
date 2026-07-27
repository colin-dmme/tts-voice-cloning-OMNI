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
from omni_tts_shared.schemas import GenerateSpeechResult, VoiceProfile

DefaultAppOpener = Callable[[Path], None]

_MISSING_RESULT_AUDIO = "Không tìm thấy file audio kết quả để phát."
_EMPTY_RESULT_AUDIO = "Kết quả này chưa có file audio để phát."
_MISSING_PROFILE_AUDIO = "Không tìm thấy file audio mẫu của profile giọng này trên đĩa."
_EMPTY_PROFILE_AUDIO = "Profile giọng này chưa có audio mẫu để nghe thử."


def profile_preview_candidates(
    profile: VoiceProfile, sample_id: str | None = None
) -> list[Path]:
    """Ordered audio candidates when previewing a saved voice profile.

    Without ``sample_id`` the profile's default sample is preferred, then the
    main sample, then any remaining extra samples. With ``sample_id`` only that
    one sample is offered, so the UI never silently plays a different take.
    """
    extras = {
        sample.sample_id: sample.audio_path
        for sample in profile.extra_samples
        if sample.sample_id
    }
    if sample_id:
        selected = extras.get(sample_id)
        return [selected] if selected is not None else []
    ordered: list[Path] = []
    default_path = extras.get(profile.default_sample_id or "")
    if default_path is not None:
        ordered.append(default_path)
    ordered.append(profile.audio_path)
    for sample in profile.extra_samples:
        if sample.audio_path not in ordered:
            ordered.append(sample.audio_path)
    return ordered


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

    def play_profile(self, profile: VoiceProfile, sample_id: str | None = None) -> Path:
        """Play a saved voice profile's reference audio — no synthesis involved."""
        candidates = profile_preview_candidates(profile, sample_id)
        if sample_id and not candidates:
            raise OmniTtsError(
                f"Không tìm thấy mẫu phụ '{sample_id}' trong profile {profile.name}."
            )
        return self.play_first_available(
            candidates,
            missing_message=_MISSING_PROFILE_AUDIO,
            empty_message=_EMPTY_PROFILE_AUDIO,
        )

    def play_first_available(
        self,
        candidates: Iterable[Path | str | None],
        missing_message: str = _MISSING_RESULT_AUDIO,
        empty_message: str = _EMPTY_RESULT_AUDIO,
    ) -> Path:
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
            raise OmniTtsError(missing_message)
        raise OmniTtsError(empty_message)


def _open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([command, str(path)])
