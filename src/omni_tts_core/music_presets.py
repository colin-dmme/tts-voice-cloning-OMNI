"""Private reusable music selections. Presets keep dynamic themes and explicit exclusions."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from filelock import FileLock
from pydantic import Field, ValidationError, field_validator

from omni_tts_shared.epub import MusicPoolSelection, MusicTrackId
from omni_tts_shared.errors import ConfigError


class MusicPreset(MusicPoolSelection):
    preset_id: MusicTrackId
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    created_at: str = ""
    updated_at: str = ""

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Tên preset không được để trống.")
        return value


class MusicPresetStore:
    def __init__(self, library=None):
        from omni_tts_core.chapter_music import ChapterMusicLibrary

        self.library = library or ChapterMusicLibrary()
        self.path = self.library.root / "presets.json"

    def list_presets(self) -> list[MusicPreset]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            presets = [MusicPreset.model_validate(row) for row in data["presets"]]
            if len({p.preset_id for p in presets}) != len(presets):
                raise ValueError("duplicate preset id")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigError(
                "Không đọc được preset nhạc; giữ nguyên file để kiểm tra."
            ) from exc
        return sorted(presets, key=lambda p: p.name.casefold())

    def get(self, preset_id: str | None) -> MusicPreset:
        if not preset_id:
            raise ConfigError("Hãy chọn một preset nhạc.")
        preset = next(
            (p for p in self.list_presets() if p.preset_id == preset_id), None
        )
        if preset is None:
            raise ConfigError("Preset nhạc không còn tồn tại. Hãy chọn lại preset.")
        return preset

    def save(
        self,
        name: str,
        *,
        preset_id: str | None = None,
        description: str = "",
        theme_ids=None,
        track_ids=None,
        excluded_track_ids=None,
    ) -> MusicPreset:
        self.library.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.library.root / ".presets.lock")):
            presets = self.list_presets()
            old = self.get(preset_id) if preset_id else None
            now = datetime.now(timezone.utc).isoformat()
            try:
                preset = MusicPreset(
                    preset_id=preset_id or "mix-" + uuid4().hex[:16],
                    name=name,
                    description=description,
                    theme_ids=theme_ids or [],
                    track_ids=track_ids or [],
                    excluded_track_ids=excluded_track_ids or [],
                    created_at=old.created_at if old else now,
                    updated_at=now,
                )
            except ValidationError as exc:
                raise ConfigError(
                    "Tên hoặc danh sách nhạc của preset không hợp lệ."
                ) from exc
            if any(
                p.name.casefold() == preset.name.casefold()
                and p.preset_id != preset.preset_id
                for p in presets
            ):
                raise ConfigError(
                    "Đã có preset cùng tên; chọn preset đó để cập nhật hoặc dùng tên khác."
                )
            self.library.selection_tracks(preset)
            self._write(
                [p for p in presets if p.preset_id != preset.preset_id] + [preset]
            )
            return preset

    def delete(self, preset_id: str) -> bool:
        if not self.path.exists():
            return False
        with FileLock(str(self.library.root / ".presets.lock")):
            presets = self.list_presets()
            remaining = [p for p in presets if p.preset_id != preset_id]
            if len(remaining) == len(presets):
                return False
            self._write(remaining)
            return True

    def _write(self, presets):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"version": 1, "presets": [p.model_dump() for p in presets]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)
