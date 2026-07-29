from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from omni_tts_core.authoring.schemas import (
    AiProviderSettings,
    AuthoringBrief,
    AuthoringPreset,
    AuthoringSession,
    VoiceContext,
)
from omni_tts_core.paths import project_path


class AiProviderSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_path("config/authoring_ai.json")
        self._lock = RLock()

    def load(self) -> AiProviderSettings:
        with self._lock:
            if not self.path.exists():
                return AiProviderSettings()
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                return AiProviderSettings.model_validate(payload)
            except Exception:
                return AiProviderSettings()

    def save(self, settings: AiProviderSettings) -> AiProviderSettings:
        with self._lock:
            _write_json(self.path, settings.model_dump(mode="json"))
        return settings


class AuthoringStateStore:
    """Last brief, named presets, and per-voice authoring descriptions."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_path("config/authoring_state.json")
        self._lock = RLock()

    def last_brief(self) -> AuthoringBrief:
        payload = self._read()
        try:
            return AuthoringBrief.model_validate(payload.get("last_brief", {}))
        except Exception:
            return AuthoringBrief()

    def save_last_brief(self, brief: AuthoringBrief) -> None:
        with self._lock:
            payload = self._read_unlocked()
            payload["last_brief"] = brief.model_dump(mode="json")
            self._write_unlocked(payload)

    def presets(self) -> list[AuthoringPreset]:
        payload = self._read()
        result: list[AuthoringPreset] = []
        for item in payload.get("presets", []):
            try:
                result.append(AuthoringPreset.model_validate(item))
            except Exception:
                continue
        return sorted(result, key=lambda item: item.name.casefold())

    def save_preset(
        self,
        name: str,
        brief: AuthoringBrief,
        *,
        voice_profile_id: str = "",
        dialect_id: str = "",
    ) -> AuthoringPreset:
        with self._lock:
            payload = self._read_unlocked()
            presets = [
                AuthoringPreset.model_validate(item)
                for item in payload.get("presets", [])
            ]
            existing = next(
                (item for item in presets if item.name.casefold() == name.strip().casefold()),
                None,
            )
            now = datetime.now().isoformat(timespec="seconds")
            if existing:
                preset = existing.model_copy(
                    update={
                        "brief": brief,
                        "voice_profile_id": voice_profile_id,
                        "dialect_id": dialect_id,
                        "updated_at": now,
                    }
                )
                presets = [
                    preset if item.preset_id == existing.preset_id else item
                    for item in presets
                ]
            else:
                preset = AuthoringPreset(
                    name=name,
                    brief=brief,
                    voice_profile_id=voice_profile_id,
                    dialect_id=dialect_id,
                )
                presets.append(preset)
            payload["presets"] = [
                item.model_dump(mode="json") for item in presets
            ]
            self._write_unlocked(payload)
            return preset

    def delete_preset(self, preset_id: str) -> bool:
        with self._lock:
            payload = self._read_unlocked()
            items = payload.get("presets", [])
            remaining = [
                item for item in items if str(item.get("preset_id", "")) != preset_id
            ]
            if len(remaining) == len(items):
                return False
            payload["presets"] = remaining
            self._write_unlocked(payload)
            return True

    def voice_context(self, voice_key: str) -> VoiceContext | None:
        if not voice_key:
            return None
        payload = self._read()
        item = payload.get("voice_contexts", {}).get(voice_key)
        if not isinstance(item, dict):
            return None
        try:
            return VoiceContext.model_validate(item)
        except Exception:
            return None

    def save_voice_context(self, voice_key: str, context: VoiceContext) -> None:
        if not voice_key:
            return
        with self._lock:
            payload = self._read_unlocked()
            contexts = payload.setdefault("voice_contexts", {})
            contexts[voice_key] = context.model_dump(mode="json")
            self._write_unlocked(payload)

    def _read(self) -> dict[str, Any]:
        with self._lock:
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "presets": [], "voice_contexts": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {"schema_version": 1, "presets": [], "voice_contexts": {}}

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        payload.setdefault("schema_version", 1)
        _write_json(self.path, payload)


class AuthoringSessionStore:
    def __init__(self, path: Path | None = None, max_sessions: int = 100) -> None:
        self.path = path or project_path("config/authoring_sessions.json")
        self.max_sessions = max(1, max_sessions)
        self._lock = RLock()

    def save(self, session: AuthoringSession) -> None:
        with self._lock:
            sessions = self.list_sessions()
            sessions = [
                item for item in sessions if item.session_id != session.session_id
            ]
            sessions.insert(0, session)
            _write_json(
                self.path,
                {
                    "schema_version": 1,
                    "sessions": [
                        item.model_dump(mode="json")
                        for item in sessions[: self.max_sessions]
                    ],
                },
            )

    def list_sessions(self) -> list[AuthoringSession]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return []
            result: list[AuthoringSession] = []
            for item in payload.get("sessions", []):
                try:
                    result.append(AuthoringSession.model_validate(item))
                except Exception:
                    continue
            return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
