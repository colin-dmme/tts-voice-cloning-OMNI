"""Readable details for one generation-history snapshot."""

from __future__ import annotations

import json

from omni_tts_core.generation_history import GenerationHistoryEntry
from omni_tts_core.ui_presenters.pause_explanations import build_pause_explanation
from omni_tts_core.ui_presenters.settings_state import GenerationSettings


def format_history_settings(entry: GenerationHistoryEntry) -> str:
    if not entry.settings_snapshot:
        return (
            "Mục lịch sử cũ này chưa có snapshot setting.\n"
            "Các kết quả và đường dẫn cũ vẫn xem được, nhưng không thể khôi phục "
            "chính xác setting để chạy lại."
        )
    settings = GenerationSettings.from_snapshot(entry.settings_snapshot)
    pause = build_pause_explanation(entry.settings_snapshot)
    voice = (
        f"Profile: {settings.voice_profile_id or '(không còn ID)'}"
        if settings.voice_source_mode == "profile"
        else f"Giọng cố định: {settings.speaker_id or '(mặc định model)'}"
    )
    snapshot_json = json.dumps(
        entry.settings_snapshot, ensure_ascii=False, indent=2, sort_keys=True
    )
    source = str(entry.source_path) if entry.source_path else entry.source_label
    return "\n".join(
        (
            "THÔNG TIN LẦN CHẠY",
            f"Nguồn: {source}",
            f"Loại: {'Văn bản' if entry.mode == 'text' else 'File'}",
            f"Model: {settings.model_id}",
            f"Ngôn ngữ: {settings.language}",
            f"Nguồn giọng: {voice}",
            f"Tốc độ: {settings.speed}",
            f"Pitch: {settings.pitch_shift}",
            f"Thiết bị: {settings.runtime_target}",
            "",
            pause.section,
            "",
            "TOÀN BỘ SNAPSHOT SETTING",
            snapshot_json,
        )
    )
