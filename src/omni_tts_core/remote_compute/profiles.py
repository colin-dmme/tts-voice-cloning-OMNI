from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from .models import WorkerProfile, WorkerSelectionSettings


class WorkerProfileDocument(BaseModel):
    version: int = 1
    profiles: list[WorkerProfile] = Field(default_factory=list)
    selection: WorkerSelectionSettings = Field(default_factory=WorkerSelectionSettings)


class WorkerProfileStore:
    """Persist worker identities without persisting Google credentials or tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> WorkerProfileDocument:
        if not self.path.exists():
            return WorkerProfileDocument()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            return WorkerProfileDocument.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            return WorkerProfileDocument()

    def save(self, document: WorkerProfileDocument) -> None:
        normalized = self._normalize(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(normalized.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def upsert(self, profile: WorkerProfile) -> WorkerProfileDocument:
        document = self.load()
        profiles = [item for item in document.profiles if item.profile_id != profile.profile_id]
        profiles.append(profile)
        profiles.sort(key=lambda item: (item.label.casefold(), item.profile_id))
        document.profiles = profiles
        if not document.selection.selected_profile_id:
            document.selection.selected_profile_id = profile.profile_id
        self.save(document)
        return self.load()

    def remove(self, profile_id: str) -> WorkerProfileDocument:
        document = self.load()
        document.profiles = [
            item for item in document.profiles if item.profile_id != profile_id
        ]
        if document.selection.selected_profile_id == profile_id:
            document.selection.selected_profile_id = (
                document.profiles[0].profile_id if document.profiles else ""
            )
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
        if selected and selected not in seen:
            selected = profiles[0].profile_id if profiles else ""
        return WorkerProfileDocument(
            profiles=profiles,
            selection=WorkerSelectionSettings(
                selected_profile_id=selected,
                switch_policy=document.selection.switch_policy,
            ),
        )
