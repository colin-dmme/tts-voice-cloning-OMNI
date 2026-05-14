from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from omni_tts_core.paths import ensure_dir
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import VoiceProfile


class VoiceProfileManager:
    def __init__(
        self,
        profiles_dir: Path | None = None,
        samples_dir: Path | None = None,
    ) -> None:
        self.profiles_dir = profiles_dir or ensure_dir("voices/profiles")
        self.samples_dir = samples_dir or ensure_dir("voices/samples")

    def list_profiles(self) -> list[VoiceProfile]:
        profiles = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            profiles.append(self._read_profile(path))
        return profiles

    def get_profile(self, profile_id: str) -> VoiceProfile:
        path = self._profile_path(profile_id)
        if not path.exists():
            raise ConfigError(f"Không tìm thấy profile giọng: {profile_id}")
        return self._read_profile(path)

    def save_profile(
        self,
        name: str,
        audio_path: Path,
        transcript: str,
        language: str = "vi",
        project: str = "",
        notes: str = "",
        profile_id: str | None = None,
    ) -> VoiceProfile:
        if not name.strip():
            raise ConfigError("Tên profile giọng không được để trống.")
        if not audio_path.exists():
            raise ConfigError(f"Không tìm thấy file giọng mẫu: {audio_path}")
        now = datetime.now().isoformat(timespec="seconds")
        resolved_id = profile_id or _new_profile_id(name)
        existing = self._load_if_exists(resolved_id)
        sample_path = self._copy_sample(audio_path, resolved_id)
        profile = VoiceProfile(
            profile_id=resolved_id,
            name=name.strip(),
            audio_path=sample_path,
            transcript=transcript.strip(),
            language=language if language in {"vi", "en"} else "vi",
            project=project.strip(),
            notes=notes.strip(),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._write_profile(profile)
        return profile

    def delete_profile(self, profile_id: str, remove_sample: bool = False) -> None:
        profile = self.get_profile(profile_id)
        self._profile_path(profile_id).unlink(missing_ok=True)
        if remove_sample and profile.audio_path.exists():
            profile.audio_path.unlink(missing_ok=True)

    def _copy_sample(self, audio_path: Path, profile_id: str) -> Path:
        target = self.samples_dir / f"{profile_id}{audio_path.suffix.lower()}"
        if audio_path.resolve() != target.resolve():
            shutil.copy2(audio_path, target)
        return target

    def _read_profile(self, path: Path) -> VoiceProfile:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Profile giọng không hợp lệ: {path}") from exc
        return VoiceProfile.model_validate(data)

    def _write_profile(self, profile: VoiceProfile) -> None:
        path = self._profile_path(profile.profile_id)
        data = profile.model_dump(mode="json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_if_exists(self, profile_id: str) -> VoiceProfile | None:
        path = self._profile_path(profile_id)
        if not path.exists():
            return None
        return self._read_profile(path)

    def _profile_path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.json"


def _new_profile_id(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name)
    slug = "-".join(part for part in slug.split("-") if part)[:40]
    return f"{slug or 'voice'}-{uuid4().hex[:8]}"
