from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


TagDensity = Literal["very_light", "light", "medium"]
VoicePresentation = Literal["auto", "female", "male", "neutral"]


class AuthoringFeatureSelection(BaseModel):
    """Strict allow-list for one provider-neutral performance dimension."""

    enabled: bool = True
    allowed_values: list[str] = Field(default_factory=list)

    @field_validator("allowed_values")
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class AuthoringControlScope(BaseModel):
    """Dimensions and values an AI director is allowed to use."""

    features: dict[str, AuthoringFeatureSelection] = Field(default_factory=dict)

    def selection(self, feature_key: str) -> AuthoringFeatureSelection:
        return self.features.get(
            feature_key,
            AuthoringFeatureSelection(enabled=False),
        )


class VoiceContext(BaseModel):
    """Resolved voice information supplied to an authoring model."""

    profile_id: str = ""
    voice_id: str = ""
    display_name: str = ""
    presentation: VoicePresentation = "auto"
    language: str = "auto"
    project: str = ""
    notes: str = ""
    description: str = ""
    source: str = "default"

    @property
    def summary(self) -> str:
        parts = [self.display_name or self.voice_id or "Giọng chưa đặt tên"]
        presentation_labels = {
            "auto": "chưa xác định nam/nữ",
            "female": "giọng nữ",
            "male": "giọng nam",
            "neutral": "giọng trung tính",
        }
        parts.append(presentation_labels[self.presentation])
        if self.description:
            parts.append(self.description)
        elif self.notes:
            parts.append(self.notes)
        return " · ".join(part for part in parts if part)


class AuthoringBrief(BaseModel):
    """User intent independent from Gemini, Higgs, or any GUI toolkit."""

    content_type: str = "science_explainer"
    platform: str = "youtube"
    segment_role: str = "hook"
    target_audience: str = ""
    narrator_style: str = "engaging"
    tag_density: TagDensity = "light"
    preserve_wording: bool = True
    allow_punctuation_changes: bool = False
    allow_vocal_sfx: bool = False
    control_scope: AuthoringControlScope = Field(default_factory=AuthoringControlScope)
    candidate_count: int = Field(default=2, ge=1, le=4)
    extra_direction: str = ""

    @field_validator(
        "content_type",
        "platform",
        "segment_role",
        "target_audience",
        "narrator_style",
        "extra_direction",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PerformanceDecision(BaseModel):
    """Provider-neutral performance intent for one source sentence."""

    sentence_index: int = Field(ge=0)
    emotion: str = ""
    style: str = ""
    pace: str = "default"
    pitch: str = "default"
    expressiveness: str = "default"
    pause_after: str = "none"
    sfx_before: str = ""
    sfx_cue: str = ""
    importance: int = Field(default=3, ge=1, le=5)
    reason: str = ""

    @field_validator(
        "emotion",
        "style",
        "pace",
        "pitch",
        "expressiveness",
        "pause_after",
        "sfx_before",
        "sfx_cue",
        "reason",
    )
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return value.strip()


class PerformancePlan(BaseModel):
    decisions: list[PerformanceDecision] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class AuthoringCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: uuid4().hex)
    parent_candidate_id: str = ""
    label: str = ""
    rendered_text: str
    plan: PerformancePlan
    validation_messages: list[str] = Field(default_factory=list)
    ai_provider: str = "gemini"
    ai_model: str = ""
    prompt_version: str = "1"
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class AuthoringSession(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    source_hash: str
    source_text: str
    dialect_id: str
    brief: AuthoringBrief
    voice_context: VoiceContext
    candidates: list[AuthoringCandidate] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class AuthoringSourceLineage(BaseModel):
    """Links a rendered candidate back to the immutable source it came from."""

    rendered_hash: str
    source_hash: str
    source_text: str
    dialect_id: str
    session_id: str = ""
    candidate_id: str = ""
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class AuthoringSourceResolution(BaseModel):
    source_text: str
    source_hash: str
    mode: Literal["current", "lineage", "recovered_markup"] = "current"
    note: str = ""
    session_id: str = ""
    candidate_id: str = ""


class AuthoringPreset(BaseModel):
    preset_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    brief: AuthoringBrief
    voice_profile_id: str = ""
    dialect_id: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Tên preset không được để trống.")
        return clean


class AiProviderSettings(BaseModel):
    provider_id: str = "gemini"
    model: str = "gemini-3.6-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    timeout_seconds: float = Field(default=120.0, ge=5.0, le=900.0)
    max_output_tokens: int = Field(default=4096, ge=0, le=65536)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_key_tries: int = Field(default=5, ge=1, le=20)
    max_busy_retries: int = Field(default=2, ge=0, le=8)

    @field_validator("provider_id", "model", "base_url")
    @classmethod
    def normalize_required_string(cls, value: str) -> str:
        return value.strip()
