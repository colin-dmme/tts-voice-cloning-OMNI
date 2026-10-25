"""Provider-neutral EPUB reading options shared by GUI, core and MCP."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChapterMusicOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    track_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    volume_percent: int = Field(default=30, ge=0, le=100)
    between_chapters: bool = True
    after_title: bool = False
    fade_in_ms: int = Field(default=120, ge=0, le=2000)
    fade_out_ms: int = Field(default=350, ge=0, le=3000)


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
