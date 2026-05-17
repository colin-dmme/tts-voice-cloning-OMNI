from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import get_args
from uuid import uuid4

from omni_tts_core.audio.wav_tools import convert_to_wav_24k_mono, load_audio_info
from omni_tts_core.paths import ensure_dir, project_path
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.schemas import AudioSampleMeta, LanguageCode, ProfileSaveWarning, VoiceProfile


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
    ) -> tuple[VoiceProfile, list[ProfileSaveWarning]]:
        if not name.strip():
            raise ConfigError("Tên profile giọng không được để trống.")
        if not audio_path.exists():
            raise ConfigError(f"Không tìm thấy file giọng mẫu: {audio_path}")
        now = datetime.now().isoformat(timespec="seconds")
        resolved_id = profile_id or _new_profile_id(name)
        existing = self._load_if_exists(resolved_id)
        dst = self.samples_dir / f"{resolved_id}.wav"
        is_new_file = audio_path.resolve() != dst.resolve()
        if is_new_file:
            convert_to_wav_24k_mono(audio_path, dst)
        duration, sr = load_audio_info(dst)
        if duration < 1.5:
            if is_new_file:
                dst.unlink(missing_ok=True)
            raise ConfigError(
                f"File giọng mẫu quá ngắn ({duration:.1f}s). Cần ít nhất 1.5 giây."
            )
        if duration > 30.0:
            if is_new_file:
                dst.unlink(missing_ok=True)
            raise ConfigError(
                f"File giọng mẫu quá dài ({duration:.1f}s). Tối đa 30 giây."
            )
        clean_transcript = transcript.strip()
        warnings = _collect_warnings(duration, clean_transcript)
        valid_langs = get_args(LanguageCode)
        profile = VoiceProfile(
            profile_id=resolved_id,
            name=name.strip(),
            audio_path=dst,
            transcript=clean_transcript,
            language=language if language in valid_langs else "vi",
            project=project.strip(),
            notes=notes.strip(),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            duration_seconds=duration,
            sample_rate=sr,
        )
        self._write_profile(profile)
        return profile, warnings

    def add_sample(
        self,
        profile_id: str,
        audio_path: Path,
        transcript: str = "",
        role: str = "neutral",
        sample_id: str | None = None,
    ) -> tuple[VoiceProfile, list[ProfileSaveWarning]]:
        profile = self.get_profile(profile_id)
        if len(profile.extra_samples) >= 2:
            raise ConfigError("Mỗi profile chỉ được tối đa 2 mẫu phụ (tổng cộng 3 mẫu).")
        if not audio_path.exists():
            raise ConfigError(f"Không tìm thấy file: {audio_path}")
        dst = self._next_extra_path(profile_id, profile)
        convert_to_wav_24k_mono(audio_path, dst)
        duration, sr = load_audio_info(dst)
        if duration < 1.5:
            dst.unlink(missing_ok=True)
            raise ConfigError(f"File giọng mẫu quá ngắn ({duration:.1f}s). Cần ít nhất 1.5 giây.")
        if duration > 30.0:
            dst.unlink(missing_ok=True)
            raise ConfigError(f"File giọng mẫu quá dài ({duration:.1f}s). Tối đa 30 giây.")
        clean_transcript = transcript.strip()
        warnings = _collect_warnings(duration, clean_transcript)
        existing_ids = {s.sample_id for s in profile.extra_samples}
        auto_id = sample_id or _make_sample_id(role, duration, existing_ids)
        new_sample = AudioSampleMeta(
            sample_id=auto_id,
            role=role,
            audio_path=dst,
            transcript=clean_transcript,
            duration_seconds=duration,
            sample_rate=sr,
        )
        updated = profile.model_copy(
            update={"extra_samples": list(profile.extra_samples) + [new_sample]}
        )
        self._write_profile(updated)
        return updated, warnings

    def remove_sample(self, profile_id: str, sample_index: int) -> VoiceProfile:
        if sample_index < 1:
            raise ConfigError("Không thể xóa mẫu chính (index 0).")
        profile = self.get_profile(profile_id)
        if sample_index > len(profile.extra_samples):
            raise ConfigError(f"Mẫu phụ không tồn tại tại vị trí {sample_index}.")
        sample = profile.extra_samples[sample_index - 1]
        sample.audio_path.unlink(missing_ok=True)
        new_extra = [s for i, s in enumerate(profile.extra_samples) if i != sample_index - 1]
        new_default = profile.default_sample_id
        if new_default == sample.sample_id:
            new_default = ""
        updated = profile.model_copy(
            update={"extra_samples": new_extra, "default_sample_id": new_default}
        )
        self._write_profile(updated)
        return updated

    def set_default_sample(self, profile_id: str, sample_id: str) -> VoiceProfile:
        profile = self.get_profile(profile_id)
        valid_ids = {""} | {s.sample_id for s in profile.extra_samples}
        if sample_id not in valid_ids:
            raise ConfigError(f"Sample không tồn tại: {sample_id}")
        updated = profile.model_copy(update={"default_sample_id": sample_id})
        self._write_profile(updated)
        return updated

    def delete_profile(self, profile_id: str, remove_sample: bool = False) -> None:
        profile = self.get_profile(profile_id)
        self._profile_path(profile_id).unlink(missing_ok=True)
        if remove_sample:
            if profile.audio_path.exists():
                profile.audio_path.unlink(missing_ok=True)
            for sample in profile.extra_samples:
                if sample.audio_path.exists():
                    sample.audio_path.unlink(missing_ok=True)

    def _read_profile(self, path: Path) -> VoiceProfile:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Profile giọng không hợp lệ: {path}") from exc
        profile = VoiceProfile.model_validate(data)
        return self._normalize_paths(profile)

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

    def _next_extra_path(self, profile_id: str, profile: VoiceProfile) -> Path:
        index = 1
        while True:
            candidate = self.samples_dir / f"{profile_id}_extra{index}.wav"
            if not candidate.exists():
                return candidate
            index += 1

    def _normalize_paths(self, profile: VoiceProfile) -> VoiceProfile:
        extra_samples = [
            sample.model_copy(update={"audio_path": self._normalize_audio_path(sample.audio_path)})
            for sample in profile.extra_samples
        ]
        return profile.model_copy(
            update={
                "audio_path": self._normalize_audio_path(profile.audio_path),
                "extra_samples": extra_samples,
            }
        )

    def _normalize_audio_path(self, value: Path) -> Path:
        if value.exists():
            return value
        if not value.is_absolute():
            candidate = project_path(value)
            if candidate.exists():
                return candidate
        sample_candidate = self.samples_dir / value.name
        if value.name and sample_candidate.exists():
            return sample_candidate
        return project_path(value) if not value.is_absolute() else value


def _new_profile_id(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name)
    slug = "-".join(part for part in slug.split("-") if part)[:40]
    return f"{slug or 'voice'}-{uuid4().hex[:8]}"


def _make_sample_id(role: str, duration: float, existing_ids: set[str]) -> str:
    base = f"{role}_{int(duration)}s"
    if base not in existing_ids:
        return base
    return f"{base}_b"


def _collect_warnings(duration: float, transcript: str) -> list[ProfileSaveWarning]:
    warnings: list[ProfileSaveWarning] = []
    if duration < 3.0:
        warnings.append(ProfileSaveWarning(
            code="short",
            message=f"Audio khá ngắn ({duration:.1f}s). Để clone giọng tốt hơn, nên dùng ít nhất 3 giây.",
        ))
    elif duration > 15.0:
        warnings.append(ProfileSaveWarning(
            code="long",
            message=f"Audio khá dài ({duration:.1f}s). Nhiều model hoạt động tốt nhất với 3–15 giây.",
        ))
    if not transcript:
        warnings.append(ProfileSaveWarning(
            code="no_transcript",
            message="Chưa có transcript. Một số engine (VieNeu Standard, Qwen3-TTS) cần transcript để clone giọng chính xác.",
        ))
    return warnings
