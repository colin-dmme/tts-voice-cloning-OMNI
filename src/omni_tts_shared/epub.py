"""Provider-neutral EPUB reading options shared by GUI, core and MCP."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MusicTrackId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")]
MusicBoundaryKey = Annotated[str, Field(pattern=r"^(title|chapter):[1-9][0-9]{0,5}$")]
MusicDurationMode = Literal["fit_pause", "full_track"]
EpubBreakKind = Literal["title", "chapter"]


class EpubBreakOptions(BaseModel):
    """One boundary owns its type, timing and fades; full music replaces its time."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["none", "silence", "music"] = "silence"
    duration_ms: int = Field(
        default=2500,
        ge=0,
        le=10000,
        description="Số giây cố định của nhịp; không áp dụng khi mode=music và duration_mode=full_track.",
    )
    duration_mode: MusicDurationMode = "fit_pause"
    fade_in_ms: int = Field(default=120, ge=0, le=2000)
    fade_out_ms: int = Field(default=350, ge=0, le=3000)

    @property
    def trigger_ms(self) -> int:
        if self.mode == "none":
            return 0
        if self.mode == "music" and self.duration_mode == "full_track":
            return max(1, self.duration_ms)
        return self.duration_ms


class MusicPoolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme_ids: list[MusicTrackId] = Field(default_factory=list, max_length=1000)
    track_ids: list[MusicTrackId] = Field(default_factory=list, max_length=10000)
    excluded_track_ids: list[MusicTrackId] = Field(
        default_factory=list, max_length=10000
    )

    @field_validator("theme_ids", "track_ids", "excluded_track_ids")
    @classmethod
    def unique_ids(cls, values):
        return list(dict.fromkeys(values))


class ChapterMusicOptions(MusicPoolSelection):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    track_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    selection_mode: Literal["fixed", "random_theme", "random_selection", "preset"] = (
        "fixed"
    )
    preset_id: MusicTrackId | None = None
    duration_mode: MusicDurationMode = "fit_pause"
    theme: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    random_seed: int = Field(default=0, ge=0, le=2147483647)
    track_overrides: dict[MusicBoundaryKey, MusicTrackId] = Field(
        default_factory=dict, max_length=20000
    )
    volume_percent: int = Field(default=30, ge=0, le=100)
    between_chapters: bool = True
    after_title: bool = False
    fade_in_ms: int = Field(default=120, ge=0, le=2000)
    fade_out_ms: int = Field(default=350, ge=0, le=3000)


class EpubContentOptions(BaseModel):
    """Book content is filtered before any provider normalization or SRT timing."""

    model_config = ConfigDict(extra="forbid")
    skip_references: bool = True
    url_mode: Literal["skip", "domain", "read"] = "skip"
    read_notes: bool = True
    han_mode: Literal["prefer_vietnamese", "warn", "keep"] = "prefer_vietnamese"
    han_readings: dict[str, str] = Field(default_factory=dict, max_length=1000)
    include_frontmatter: bool = True
    include_appendices: bool = True
    include_technical_notes: bool = False
    export_references: bool = True

    @field_validator("han_readings")
    @classmethod
    def valid_readings(cls, values):
        import re

        cleaned = {}
        for written, spoken in values.items():
            written, spoken = written.strip(), spoken.strip()
            if not written or len(written) > 120 or not spoken or len(spoken) > 500:
                raise ValueError(
                    "Cách đọc chữ Hán cần có cụm gốc và cách đọc, tối đa 120/500 ký tự."
                )
            if not re.search(
                r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]",
                written,
            ):
                raise ValueError("Cụm gốc trong han_readings phải chứa chữ Hán.")
            cleaned[written] = spoken
        return cleaned


class EpubOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_start: int = Field(default=1, ge=1, le=100000)
    chapter_end: int = Field(default=0, ge=0, le=100000, description="0 = hết sách")
    read_titles: bool = True
    include_volumes: bool = True
    output_mode: Literal["chapters", "merged"] = "chapters"
    title_pause_ms: int = Field(default=1200, ge=0, le=10000)
    chapter_pause_ms: int = Field(default=2500, ge=0, le=10000)
    scene_pause_ms: int = Field(default=1200, ge=0, le=10000)
    volume_pause_ms: int = Field(default=1800, ge=0, le=10000)
    music: ChapterMusicOptions = Field(default_factory=ChapterMusicOptions)
    content: EpubContentOptions = Field(default_factory=EpubContentOptions)
    breaks: dict[EpubBreakKind, EpubBreakOptions] = Field(
        default_factory=dict,
        description="Thiết lập từng nhịp title/chapter: none/silence/music, thời lượng và fade. Có khóa này thì ưu tiên hơn các trường pause/music cũ của cùng nhịp. music chứa nguồn bài/nhóm, âm lượng và chỉ định của agent.",
    )

    def break_for(self, kind: EpubBreakKind) -> EpubBreakOptions:
        if kind in self.breaks:
            return self.breaks[kind]
        duration = self.title_pause_ms if kind == "title" else self.chapter_pause_ms
        musical = self.music.enabled and (
            self.music.after_title if kind == "title" else self.music.between_chapters
        )
        return EpubBreakOptions(
            mode="none" if duration == 0 else ("music" if musical else "silence"),
            duration_ms=duration,
            duration_mode=self.music.duration_mode,
            fade_in_ms=self.music.fade_in_ms,
            fade_out_ms=self.music.fade_out_ms,
        )

    def music_for(self, kind: EpubBreakKind) -> ChapterMusicOptions:
        boundary = self.break_for(kind)
        enabled = (
            boundary.mode == "music"
            and boundary.trigger_ms > 0
            and (kind != "title" or self.read_titles)
        )
        return self.music.model_copy(
            update={
                "enabled": enabled,
                "after_title": kind == "title",
                "between_chapters": kind == "chapter",
                "duration_mode": boundary.duration_mode,
                "fade_in_ms": boundary.fade_in_ms,
                "fade_out_ms": boundary.fade_out_ms,
            }
        )

    def uses_music(self) -> bool:
        return any(self.music_for(kind).enabled for kind in ("title", "chapter"))

    @model_validator(mode="after")
    def valid_range(self):
        if self.chapter_end and self.chapter_end < self.chapter_start:
            raise ValueError(
                "Chương kết thúc phải từ chương bắt đầu trở đi, hoặc 0 để đọc hết."
            )
        return self


EPUB_PAUSE_FIELDS = (
    ("title_pause_ms", "Nghỉ sau tên chương", 1200),
    ("chapter_pause_ms", "Nghỉ giữa hai chương", 2500),
    ("scene_pause_ms", "Nghỉ chuyển cảnh", 1200),
    ("volume_pause_ms", "Nghỉ sau tên quyển", 1800),
)
