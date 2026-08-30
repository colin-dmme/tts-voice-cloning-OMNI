"""Persistence for DesignedVoice entities (OmniVoice Voice Design).

Mirrors VoiceProfileManager but for audio-less, description-only voices stored
as JSON under ``voices/designed/``. All list/filter/group logic lives in
``voice_library`` — this store only does CRUD.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import get_args
from uuid import uuid4

from omni_tts_core.paths import ensure_dir
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import DesignedVoice, LanguageCode


class DesignedVoiceStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self.store_dir = store_dir or ensure_dir("voices/designed")

    def list_voices(self) -> list[DesignedVoice]:
        voices = []
        for path in sorted(self.store_dir.glob("*.json")):
            voices.append(self._read(path))
        return voices

    def get_voice(self, voice_id: str) -> DesignedVoice:
        path = self._path(voice_id)
        if not path.exists():
            raise ConfigError(f"Không tìm thấy giọng thiết kế: {voice_id}")
        return self._read(path)

    def save_voice(
        self,
        name: str,
        instruct: str,
        language: str = "vi",
        project: str = "",
        tags: list[str] | None = None,
        notes: str = "",
        voice_id: str | None = None,
    ) -> DesignedVoice:
        if not name.strip():
            raise ConfigError("Tên giọng thiết kế không được để trống.")
        if not instruct.strip():
            raise ConfigError("Mô tả giọng (instruct) không được để trống.")
        now = datetime.now().isoformat(timespec="seconds")
        resolved_id = voice_id or _new_voice_id(name)
        existing = self._load_if_exists(resolved_id)
        valid_langs = get_args(LanguageCode)
        voice = DesignedVoice(
            designed_voice_id=resolved_id,
            name=name.strip(),
            instruct=instruct.strip(),
            language=language if language in valid_langs else "vi",
            project=project.strip(),
            tags=_clean_tags(tags),
            notes=notes.strip(),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._write(voice)
        return voice

    def delete_voice(self, voice_id: str) -> None:
        self._path(voice_id).unlink(missing_ok=True)

    def _read(self, path: Path) -> DesignedVoice:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Giọng thiết kế không hợp lệ: {path}") from exc
        return DesignedVoice.model_validate(data)

    def _write(self, voice: DesignedVoice) -> None:
        path = self._path(voice.designed_voice_id)
        data = voice.model_dump(mode="json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_if_exists(self, voice_id: str) -> DesignedVoice | None:
        path = self._path(voice_id)
        return self._read(path) if path.exists() else None

    def _path(self, voice_id: str) -> Path:
        return self.store_dir / f"{voice_id}.json"


def _new_voice_id(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name)
    slug = "-".join(part for part in slug.split("-") if part)[:40]
    return f"{slug or 'design'}-{uuid4().hex[:8]}"


def _clean_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: dict[str, None] = {}
    for tag in tags:
        cleaned = str(tag).strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)
