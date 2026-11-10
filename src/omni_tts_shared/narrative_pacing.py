"""Options for narrative pacing: tiered pauses and cross-faded music bridges.

Pacing runs after a merged text job has been assembled (or on an existing
audio + SRT pair). It only inserts time inside silences that already exist, so
speech is never cut, and SRT timings are shifted on the same timeline.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from omni_tts_shared.epub import MusicPoolSelection

_TRACK_ID = r"^[a-z0-9][a-z0-9_-]{0,79}$"
# Pause layers that accept a Min–Max range (see omni_tts_core.rhythm.layers).
RANGE_LAYERS = (
    "comma", "clause", "ellipsis", "sentence_end", "question_end", "short_sentence",
    "connector", "paragraph", "question", "emphasis", "subtopic", "section",
)


class NarrativeMusicOptions(MusicPoolSelection):
    """Short music bridges between major sections, plus an optional series theme."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    selection_mode: Literal["fixed", "random_theme", "random_selection", "preset"] = "random_theme"
    track_id: str | None = Field(default=None, pattern=_TRACK_ID)
    preset_id: str | None = Field(default=None, pattern=_TRACK_ID)
    theme: str | None = Field(default=None, pattern=_TRACK_ID)
    random_seed: int = Field(default=0, ge=0, le=2147483647)
    # Music level relative to the narration's speech level (approximate loudness).
    level_db: float = Field(default=-3.5, ge=-30.0, le=0.0)
    # Automatic placement: about one bridge per interval, snapped to topic changes.
    interval_minutes: float = Field(default=10.0, ge=2.0, le=60.0)
    # 1-based paragraph numbers that must start right after a bridge. When given,
    # automatic placement is skipped (agent/editor knows the structure best).
    bridge_before_units: list[int] = Field(default_factory=list, max_length=500)
    # False = only the listed bridges (an empty list then means no bridges).
    auto_bridges: bool = True
    # Two bridge types. Short (sting, ~4-5 s heard): marks a new part every
    # interval_minutes. Long (bumper, ~10-11 s heard): marks the big turns of
    # the episode, about one per major_interval_minutes, plus the closing.
    # Cross-fade: music rises under the last words, plays a solo, then sinks
    # under the first words of the next paragraph.
    overlap_in_ms: int = Field(default=1000, ge=0, le=4000)
    overlap_out_ms: int = Field(default=1600, ge=0, le=6000)
    min_solo_ms: int = Field(default=2000, ge=500, le=10000)
    # Short bridges never hold a solo longer than this, even with longer tracks.
    max_solo_ms: int = Field(default=3000, ge=500, le=10000)
    major_enabled: bool = True
    major_interval_minutes: float = Field(default=30.0, ge=5.0, le=180.0)
    # 1-based paragraph numbers for long bridges; they are added to the bridges
    # if missing. When given, automatic promotion is skipped.
    major_before_units: list[int] = Field(default_factory=list, max_length=200)
    # Library tracks for long bridges; empty (and no major_theme) = an excerpt of
    # theme_track_id (the series signature), or the short pool without a theme.
    major_track_ids: list[str] = Field(default_factory=list, max_length=50)
    # Or a library theme group for long bridges (e.g. "chuyen-chuong"). Tracks
    # tagged "closing" are kept for the closing bridge.
    major_theme: str | None = Field(default=None, pattern=_TRACK_ID)
    # Exact track per bridge: {paragraph number (1-based): track_id}. Lets an
    # editor/agent match the music to the mood of the part that follows.
    bridge_tracks: dict[int, str] = Field(default_factory=dict, max_length=500)
    major_overlap_in_ms: int = Field(default=1500, ge=0, le=5000)
    major_overlap_out_ms: int = Field(default=2500, ge=0, le=8000)
    major_solo_ms: int = Field(default=6000, ge=1000, le=20000)
    # Series theme for intro/outro. None disables both.
    theme_track_id: str | None = Field(default=None, pattern=_TRACK_ID)
    # The opening hook stays dry. The theme enters before this paragraph
    # (1-based); None = detect the series/channel introduction automatically.
    intro_before_unit: int | None = Field(default=None, ge=2)
    hook_min_seconds: float = Field(default=15.0, ge=0.0, le=300.0)
    outro_enabled: bool = True

    @field_validator("major_track_ids")
    @classmethod
    def track_ids_valid(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(_TRACK_ID, v) for v in values):
            raise ValueError("major_track_ids chứa mã nhạc không hợp lệ.")
        return list(dict.fromkeys(values))

    @field_validator("bridge_tracks")
    @classmethod
    def bridge_tracks_valid(cls, values: dict[int, str]) -> dict[int, str]:
        if any(k < 2 or not re.fullmatch(_TRACK_ID, v) for k, v in values.items()):
            raise ValueError("bridge_tracks cần số đoạn từ 2 và mã nhạc hợp lệ.")
        return values

    @field_validator("bridge_before_units", "major_before_units")
    @classmethod
    def positive_sorted(cls, values: list[int]) -> list[int]:
        if any(v < 2 for v in values):
            raise ValueError("Số đoạn đặt nhạc bắt đầu từ 2.")
        return sorted(set(values))


class NarrativePacingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # "pacing_only": the old pause settings stay in charge and pacing only
    # stretches afterwards (original behaviour). "full": Nhịp đọc owns every
    # pause layer; Core picks one owner per layer from the model's capability
    # profile and locks the overlapping old controls.
    scope: Literal["pacing_only", "full"] = "pacing_only"
    # Model-specific switches declared by the capability profiles, e.g.
    # {"kokoro_pause_mode": "library", "omnivoice_keep_long_silence": "on"}.
    # Kept for every model; only the matching model reads its keys.
    model_switches: dict[str, str] = Field(default_factory=dict, max_length=50)
    # Optional Min–Max total silence per layer, e.g. {"sentence_end": [450, 600]}.
    # Each pause draws its own value in the range; a layer without a range uses
    # its single *_pause_ms value (plus jitter between paragraphs).
    layer_ranges: dict[str, list[int]] = Field(default_factory=dict, max_length=len(RANGE_LAYERS))
    # Target total silence (ms) between paragraphs, by boundary kind.
    # Defaults follow measured read speech: between-sentence pauses about 0.6-0.7
    # of paragraph pauses, paragraph pauses about 0.75-1.35 s, longer after long
    # paragraphs (scaled by length, see paragraph_length_scaling).
    connector_pause_ms: int = Field(default=600, ge=0, le=5000)
    paragraph_pause_ms: int = Field(default=850, ge=0, le=5000)
    question_pause_ms: int = Field(default=1000, ge=0, le=5000)
    emphasis_pause_ms: int = Field(default=1050, ge=0, le=5000)
    subtopic_pause_ms: int = Field(default=1300, ge=0, le=5000)
    paragraph_length_scaling: bool = True
    jitter_ms: int = Field(default=70, ge=0, le=500)
    # Section layer: a clear silence (no music) where the topic changes, between
    # the music parts. Chosen from topic-shift scores (vocabulary change +
    # markers), about one per interval; an explicit list overrides it.
    sections_enabled: bool = True
    section_pause_ms: int = Field(default=2000, ge=0, le=8000)
    section_interval_minutes: float = Field(default=3.5, ge=1.0, le=30.0)
    section_before_units: list[int] = Field(default_factory=list, max_length=1000)
    # Inside paragraphs: lengthen only sentence-final pauses (commas untouched).
    sentence_pauses_enabled: bool = True
    sentence_end_pause_ms: int = Field(default=520, ge=0, le=3000)
    question_end_pause_ms: int = Field(default=620, ge=0, le=3000)
    colon_pause_ms: int = Field(default=380, ge=0, le=3000)
    # Commas: only a floor. TTS often leaves 0.08-0.2 s, which sounds rushed;
    # 0 keeps commas untouched.
    comma_min_pause_ms: int = Field(default=200, ge=0, le=1500)
    # A beat around short punchy sentences ("Con người ấy là ai? Chính là ta.").
    short_sentence_pause_ms: int = Field(default=700, ge=0, le=3000)
    seed: int = Field(default=7, ge=0, le=2147483647)
    music: NarrativeMusicOptions = Field(default_factory=NarrativeMusicOptions)

    @field_validator("layer_ranges")
    @classmethod
    def ranges_valid(cls, values: dict[str, list[int]]) -> dict[str, list[int]]:
        clean: dict[str, list[int]] = {}
        for layer, pair in values.items():
            if layer not in RANGE_LAYERS:
                raise ValueError(f"layer_ranges: tầng '{layer}' không hỗ trợ Min–Max.")
            if len(pair) != 2 or not 0 <= pair[0] <= pair[1] <= 8000:
                raise ValueError(f"layer_ranges[{layer}] cần [min, max] với 0 ≤ min ≤ max ≤ 8000 ms.")
            clean[layer] = [int(pair[0]), int(pair[1])]
        return clean

    @field_validator("section_before_units")
    @classmethod
    def sections_sorted(cls, values: list[int]) -> list[int]:
        if any(v < 2 for v in values):
            raise ValueError("section_before_units dùng số đoạn bắt đầu từ 2.")
        return sorted(set(values))
