from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from omni_tts_core.paths import ensure_dir
from omni_tts_shared.errors import ConfigError
from omni_tts_shared.pronunciation import PronunciationPreset, PronunciationRule


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class PronunciationPresetStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self.store_dir = store_dir or ensure_dir("pronunciation/presets")
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def list_presets(self) -> list[PronunciationPreset]:
        presets: list[PronunciationPreset] = []
        for path in sorted(self.store_dir.glob("*.json")):
            try:
                presets.append(self._read(path))
            except ConfigError:
                continue
        return sorted(presets, key=lambda item: (item.project.casefold(), item.name.casefold()))

    def get(self, preset_id: str) -> PronunciationPreset:
        path = self._path_for(preset_id)
        if not path.exists():
            raise ConfigError(f"Không tìm thấy preset cách đọc: {preset_id}")
        return self._read(path)

    def save(
        self,
        *,
        name: str,
        rules: list[PronunciationRule | dict],
        project: str = "",
        tags: list[str] | None = None,
        notes: str = "",
        preset_id: str | None = None,
    ) -> PronunciationPreset:
        now = datetime.now().isoformat(timespec="seconds")
        existing = None
        if preset_id:
            try:
                existing = self.get(preset_id)
            except ConfigError:
                existing = None
        parsed_rules = [
            rule if isinstance(rule, PronunciationRule) else PronunciationRule.model_validate(rule)
            for rule in rules
        ]
        preset = PronunciationPreset(
            preset_id=preset_id or uuid4().hex,
            name=name,
            project=project,
            tags=tags or [],
            notes=notes,
            rules=parsed_rules,
            revision=(existing.revision + 1) if existing else 1,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._validate_duplicate_rules(preset)
        self._write(preset)
        return preset

    def duplicate(self, preset_id: str, name: str | None = None) -> PronunciationPreset:
        source = self.get(preset_id)
        rules = [
            rule.model_copy(update={"rule_id": uuid4().hex}) for rule in source.rules
        ]
        return self.save(
            name=name or f"{source.name} - Bản sao",
            project=source.project,
            tags=source.tags,
            notes=source.notes,
            rules=rules,
        )

    def delete(self, preset_id: str) -> bool:
        path = self._path_for(preset_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def import_file(self, path: Path) -> PronunciationPreset:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Không đọc được preset cách đọc: {path}") from exc
        preset = PronunciationPreset.model_validate(data)
        try:
            self.get(preset.preset_id)
        except ConfigError:
            preset = preset.model_copy(update={"revision": 1})
        else:
            preset = preset.model_copy(update={"preset_id": uuid4().hex, "revision": 1})
        now = datetime.now().isoformat(timespec="seconds")
        preset = preset.model_copy(update={"created_at": now, "updated_at": now})
        self._validate_duplicate_rules(preset)
        self._write(preset)
        return preset

    def export_file(self, preset_id: str, path: Path) -> Path:
        preset = self.get(preset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(preset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def _read(self, path: Path) -> PronunciationPreset:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PronunciationPreset.model_validate(data)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Preset cách đọc bị lỗi: {path}") from exc

    def _write(self, preset: PronunciationPreset) -> None:
        path = self._path_for(preset.preset_id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(preset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _path_for(self, preset_id: str) -> Path:
        value = str(preset_id or "").strip()
        if not value or not _SAFE_ID.fullmatch(value):
            raise ConfigError("ID preset cách đọc không hợp lệ.")
        return self.store_dir / f"{value}.json"

    @staticmethod
    def _validate_duplicate_rules(preset: PronunciationPreset) -> None:
        seen: dict[tuple[str, bool, str], PronunciationRule] = {}
        for rule in preset.rules:
            if not rule.enabled:
                continue
            written_key = rule.written if rule.case_sensitive else rule.written.casefold()
            key = (written_key, rule.case_sensitive, rule.match_mode)
            previous = seen.get(key)
            if previous and previous.spoken != rule.spoken:
                raise ConfigError(
                    f"Preset có hai cách đọc khác nhau cho “{rule.written}”."
                )
            seen[key] = rule