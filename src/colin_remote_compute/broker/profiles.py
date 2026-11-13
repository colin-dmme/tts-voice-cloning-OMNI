from __future__ import annotations

import json
import os
from pathlib import Path

from filelock import FileLock
from pydantic import BaseModel, Field

from .models import WorkerProfile, WorkerSelectionSettings


class WorkerProfileDocument(BaseModel):
    version: int = 1
    profiles: list[WorkerProfile] = Field(default_factory=list)
    selection: WorkerSelectionSettings = Field(default_factory=WorkerSelectionSettings)
    cpu_pool_limit: int = Field(default=4, ge=1, le=16)
    cpu_pool_local: bool = False


class WorkerProfileStore:
    """Persist worker identities without persisting Google credentials or tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = FileLock(str(path) + ".lock", timeout=10)

    def load(self) -> WorkerProfileDocument:
        if not self.path.exists():
            return WorkerProfileDocument()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            return WorkerProfileDocument.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            return WorkerProfileDocument()

    def save(self, document: WorkerProfileDocument) -> None:
        with self._lock:
            self._write(document)

    def _write(self, document: WorkerProfileDocument) -> None:
        normalized = self._normalize(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(normalized.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def upsert(self, profile: WorkerProfile) -> WorkerProfileDocument:
        with self._lock:
            document = self.load()
            profiles = [item for item in document.profiles if item.profile_id != profile.profile_id]
            profiles.append(profile)
            profiles.sort(key=lambda item: (item.label.casefold(), item.profile_id))
            document.profiles = profiles
            if not document.selection.selected_profile_id and not profile.is_pc:
                document.selection.selected_profile_id = profile.profile_id
            self._write(document)
            return self.load()

    def set_cpu_pool_limit(self, limit: int) -> None:
        with self._lock:
            values = self.load().model_dump() | {"cpu_pool_limit": limit}
            self._write(WorkerProfileDocument.model_validate(values))

    def set_cpu_pool_local(self, enabled: bool) -> None:
        with self._lock:
            document = self.load()
            document.cpu_pool_local = bool(enabled)
            self._write(document)

    def set_cpu_pool_worker(self, profile_id: str, enabled: bool) -> None:
        with self._lock:
            document = self.load()
            profile = next((item for item in document.profiles if item.profile_id == profile_id and item.is_pc), None)
            if profile is None or not profile.enabled:
                raise ValueError("Cần ghép máy trước khi đưa vào nhóm CPU.")
            profile.pool_enabled = enabled
            self._write(document)

    def remove(self, profile_id: str) -> WorkerProfileDocument:
        document = self.load()
        document.profiles = [
            item for item in document.profiles if item.profile_id != profile_id
        ]
        if document.selection.selected_profile_id == profile_id:
            document.selection.selected_profile_id = (
                next((profile.profile_id for profile in document.profiles if not profile.is_pc), "")
            )
        self.save(document)
        return self.load()

    def reorder(self, profile_ids: list[str]) -> WorkerProfileDocument:
        document = self.load()
        by_id = {profile.profile_id: profile for profile in document.profiles}
        if len(profile_ids) != len(set(profile_ids)) or set(profile_ids) != set(by_id):
            raise ValueError("Thứ tự ưu tiên phải chứa mỗi profile đúng một lần")
        document.profiles = [by_id[profile_id] for profile_id in profile_ids]
        self.save(document)
        return self.load()

    @staticmethod
    def _normalize(document: WorkerProfileDocument) -> WorkerProfileDocument:
        seen: set[str] = set()
        profiles: list[WorkerProfile] = []
        for profile in document.profiles:
            if profile.profile_id in seen:
                continue
            seen.add(profile.profile_id)
            profiles.append(profile)
        selected = document.selection.selected_profile_id
        if selected and not any(item.profile_id == selected and not item.is_pc for item in profiles):
            selected = next((item.profile_id for item in profiles if not item.is_pc), "")
        return WorkerProfileDocument(
            profiles=profiles,
            cpu_pool_limit=document.cpu_pool_limit,
            cpu_pool_local=document.cpu_pool_local,
            selection=WorkerSelectionSettings(
                selected_profile_id=selected,
                switch_policy=document.selection.switch_policy,
            ),
        )
