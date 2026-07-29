"""Validation and restore plans for replaying generation history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from omni_tts_core.generation_history import GenerationHistoryEntry
from omni_tts_core.ui_presenters.settings_state import GenerationSettings
from omni_tts_shared.errors import OmniTtsError


@dataclass(frozen=True)
class HistoryRestorePlan:
    mode: str
    settings: GenerationSettings
    source_label: str
    source_path: Path | None = None
    source_text: str = ""


def build_history_restore_plan(
    entry: GenerationHistoryEntry,
) -> HistoryRestorePlan:
    if not entry.settings_snapshot:
        raise OmniTtsError(
            "Mục lịch sử cũ này chưa có snapshot setting nên không thể khôi phục "
            "chính xác. Hãy chạy lại một lần bằng phiên bản mới."
        )
    settings = GenerationSettings.from_snapshot(entry.settings_snapshot)
    if entry.mode == "file":
        if entry.source_path is None or not entry.source_path.is_file():
            raise OmniTtsError(
                f"File nguồn không còn tồn tại: {entry.source_path or entry.source_label}"
            )
        return HistoryRestorePlan(
            mode="file",
            settings=settings,
            source_label=entry.source_label,
            source_path=entry.source_path,
        )
    if entry.mode == "text":
        if not entry.source_text.strip():
            raise OmniTtsError(
                "Mục lịch sử này không có nội dung văn bản để khôi phục."
            )
        return HistoryRestorePlan(
            mode="text",
            settings=settings,
            source_label=entry.source_label,
            source_text=entry.source_text,
        )
    raise OmniTtsError(f"Loại lịch sử không được hỗ trợ: {entry.mode}")


def restore_setting_mismatches(
    expected: GenerationSettings, actual: GenerationSettings
) -> tuple[str, ...]:
    """Fields a GUI failed to apply, excluding values restored elsewhere."""
    excluded = {
        "output_stem",
        "reference_audio_path",
        "reference_text",
        "srt_file_padding_ms",
    }
    expected_values = expected.to_snapshot()
    actual_values = actual.to_snapshot()
    return tuple(
        key
        for key, value in expected_values.items()
        if key not in excluded and actual_values.get(key) != value
    )
