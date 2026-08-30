from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


PronunciationMatchMode = Literal["whole_term", "literal"]


class PronunciationRule(BaseModel):
    rule_id: str = Field(default_factory=lambda: uuid4().hex)
    written: str
    spoken: str
    enabled: bool = True
    case_sensitive: bool = False
    match_mode: PronunciationMatchMode = "whole_term"
    priority: int = Field(default=0, ge=-1000, le=1000)
    notes: str = ""

    @model_validator(mode="after")
    def normalize_fields(self):
        self.rule_id = self.rule_id.strip() or uuid4().hex
        self.written = self.written.strip()
        self.spoken = self.spoken.strip()
        self.notes = self.notes.strip()
        if not self.written:
            raise ValueError("Từ/cụm từ gốc không được để trống.")
        if not self.spoken:
            raise ValueError("Cách đọc không được để trống.")
        return self


class PronunciationPreset(BaseModel):
    preset_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    project: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    rules: list[PronunciationRule] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    created_at: str = ""
    updated_at: str = ""

    @model_validator(mode="after")
    def normalize_fields(self):
        self.preset_id = self.preset_id.strip() or uuid4().hex
        self.name = self.name.strip()
        self.project = self.project.strip()
        self.notes = self.notes.strip()
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
        if not self.name:
            raise ValueError("Tên preset không được để trống.")
        return self


class PronunciationSelection(BaseModel):
    enabled: bool = False
    preset_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_fields(self):
        self.preset_ids = list(
            dict.fromkeys(value.strip() for value in self.preset_ids if value.strip())
        )
        self.enabled = bool(self.enabled and self.preset_ids)
        return self


class PronunciationPresetSnapshot(BaseModel):
    preset_id: str
    name: str
    revision: int
    rules: list[PronunciationRule] = Field(default_factory=list)


class PronunciationSnapshot(BaseModel):
    enabled: bool = False
    presets: list[PronunciationPresetSnapshot] = Field(default_factory=list)
    content_hash: str = ""

    @property
    def preset_ids(self) -> list[str]:
        return [preset.preset_id for preset in self.presets]

    @property
    def preset_names(self) -> list[str]:
        return [preset.name for preset in self.presets]


class PronunciationMatch(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    matched_text: str
    written: str
    spoken: str
    rule_id: str
    preset_id: str
    preset_name: str


class PronunciationConflict(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    winner_rule_id: str
    ignored_rule_ids: list[str] = Field(default_factory=list)
    message: str


class PronunciationAnalysis(BaseModel):
    original_text: str
    speech_text: str
    snapshot_hash: str = ""
    preset_ids: list[str] = Field(default_factory=list)
    preset_names: list[str] = Field(default_factory=list)
    matches: list[PronunciationMatch] = Field(default_factory=list)
    conflicts: list[PronunciationConflict] = Field(default_factory=list)
    term_count: int = 0
    match_count: int = 0
    conflict_count: int = 0


class PronunciationReport(BaseModel):
    snapshot_hash: str = ""
    preset_ids: list[str] = Field(default_factory=list)
    preset_names: list[str] = Field(default_factory=list)
    original_sha256: str
    speech_sha256: str
    term_count: int = 0
    match_count: int = 0
    conflict_count: int = 0
    matches: list[PronunciationMatch] = Field(default_factory=list)
    conflicts: list[PronunciationConflict] = Field(default_factory=list)