from __future__ import annotations

from omni_tts_shared.voice_presets import VALTEC_DEFAULT_SPEAKER, VALTEC_SPEAKERS


def valtec_speaker_label(speaker_id: str | None) -> str:
    speaker = speaker_id or VALTEC_DEFAULT_SPEAKER
    return VALTEC_SPEAKERS.get(speaker, VALTEC_SPEAKERS[VALTEC_DEFAULT_SPEAKER])
