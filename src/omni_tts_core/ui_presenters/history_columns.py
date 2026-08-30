"""Derive extra display columns for a generation-history row.

Voice and language are not stored as their own columns; they live inside the
settings snapshot. These helpers read that snapshot so the history table can show
which voice/profile and language each run used, tolerating older rows that have
no snapshot at all.
"""

from __future__ import annotations

from typing import Mapping

from omni_tts_core.generation_history import GenerationHistoryEntry
from omni_tts_shared.languages import language_label

_MISSING = "—"


def history_language_label(entry: GenerationHistoryEntry) -> str:
    """Human-readable language of the run, or ``—`` when unknown."""
    code = str(entry.settings_snapshot.get("language") or "").strip()
    return language_label(code) if code else _MISSING


def history_voice_label(
    entry: GenerationHistoryEntry,
    profile_names: Mapping[str, str] | None = None,
) -> str:
    """Which voice the run used: a profile name, a fixed voice, or ``—``.

    ``profile_names`` maps profile id → current name so deleted/renamed profiles
    still read sensibly. Falls back to the stored id when a name is unavailable.
    """
    snapshot = entry.settings_snapshot
    if not snapshot:
        return _MISSING
    mode = str(snapshot.get("voice_source_mode") or "").strip()
    if mode == "profile":
        profile_id = str(snapshot.get("voice_profile_id") or "").strip()
        if not profile_id:
            return "Profile (đã xóa)"
        names = profile_names or {}
        name = names.get(profile_id)
        return name or f"Profile #{profile_id[:8]}"
    # Fixed voice: a model preset id, a Higgs voice, or the model default.
    speaker = str(snapshot.get("speaker_id") or "").strip()
    if speaker:
        return speaker
    higgs_voice = str(snapshot.get("higgs_voice") or "").strip()
    if higgs_voice and higgs_voice != "default":
        return higgs_voice
    return "Giọng mặc định"
