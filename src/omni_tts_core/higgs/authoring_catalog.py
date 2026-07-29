from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiggsTagOption:
    """Framework-neutral metadata for one authoring action."""

    category: str
    value: str
    label: str
    description: str
    usage: str
    featured: bool = False

    @property
    def token(self) -> str:
        return f"<|{self.category}:{self.value}|>"

    @property
    def tooltip(self) -> str:
        return (
            f"{self.description}\n"
            f"Cách dùng: {self.usage}\n"
            f"Token: {self.token}"
        )


@dataclass(frozen=True)
class HiggsTagGroup:
    key: str
    label: str
    description: str
    options: tuple[HiggsTagOption, ...]


_DELIVERY_USAGE = (
    "đặt ở đầu câu cần điều khiển. Nếu câu tiếp theo cần sắc thái khác, "
    "hãy đặt tag mới ở đầu câu đó."
)
_SFX_USAGE = (
    "chèn sát ngay trước từ tượng thanh tương ứng, không để khoảng trắng; "
    "ví dụ <|sfx:laughter|>Haha."
)


def _option(
    category: str,
    value: str,
    label: str,
    description: str,
    *,
    usage: str = _DELIVERY_USAGE,
    featured: bool = False,
) -> HiggsTagOption:
    return HiggsTagOption(
        category=category,
        value=value,
        label=label,
        description=description,
        usage=usage,
        featured=featured,
    )


HIGGS_TAG_GROUPS = (
    HiggsTagGroup(
        key="emotion",
        label="Cảm xúc",
        description="Chọn sắc thái cảm xúc cho phần lời tiếp theo.",
        options=(
            _option("emotion", "elation", "Vui sướng", "Rất vui và phấn khởi."),
            _option("emotion", "amusement", "Thích thú", "Vui vẻ, có nét tinh nghịch."),
            _option("emotion", "enthusiasm", "Hào hứng", "Nhiệt tình và giàu năng lượng."),
            _option("emotion", "determination", "Quyết tâm", "Kiên định, dứt khoát."),
            _option("emotion", "pride", "Tự hào", "Tự tin và hãnh diện."),
            _option("emotion", "contentment", "Hài lòng", "Bình yên, mãn nguyện."),
            _option("emotion", "affection", "Trìu mến", "Ấm áp và giàu tình cảm."),
            _option("emotion", "relief", "Nhẹ nhõm", "Thư giãn sau khi hết căng thẳng."),
            _option("emotion", "contemplation", "Trầm tư", "Suy ngẫm, có chiều sâu."),
            _option("emotion", "confusion", "Bối rối", "Không chắc chắn, khó hiểu."),
            _option("emotion", "surprise", "Bất ngờ", "Ngạc nhiên trước điều vừa xảy ra."),
            _option("emotion", "awe", "Kinh ngạc", "Choáng ngợp, thán phục."),
            _option("emotion", "longing", "Mong nhớ", "Khao khát, nhớ nhung."),
            _option("emotion", "arousal", "Hưng phấn", "Cảm xúc kích thích, mãnh liệt."),
            _option("emotion", "anger", "Giận dữ", "Bực tức, mạnh và căng."),
            _option("emotion", "fear", "Sợ hãi", "Lo sợ, bất an."),
            _option("emotion", "disgust", "Ghê sợ", "Khó chịu, phản cảm."),
            _option("emotion", "bitterness", "Cay đắng", "Ấm ức và chua xót."),
            _option("emotion", "sadness", "Buồn bã", "Buồn, mất mát."),
            _option("emotion", "shame", "Xấu hổ", "Ngượng ngùng, ân hận."),
            _option("emotion", "helplessness", "Bất lực", "Yếu thế, không còn cách giải quyết."),
        ),
    ),
    HiggsTagGroup(
        key="style",
        label="Phong cách",
        description="Đổi cách phát giọng cho phần lời tiếp theo.",
        options=(
            _option("style", "singing", "Hát", "Đọc theo phong cách hát."),
            _option("style", "shouting", "Hô lớn", "Phát giọng lớn, có lực."),
            _option("style", "whispering", "Thì thầm", "Phát giọng nhỏ và kín đáo."),
        ),
    ),
    HiggsTagGroup(
        key="prosody",
        label="Nhịp & biểu cảm",
        description="Điều khiển tốc độ, cao độ, độ biểu cảm và khoảng nghỉ.",
        options=(
            _option("prosody", "speed_very_slow", "Rất chậm", "Tốc độ khoảng 0,65 lần."),
            _option("prosody", "speed_slow", "Chậm", "Tốc độ khoảng 0,85 lần."),
            _option("prosody", "speed_fast", "Nhanh", "Tốc độ khoảng 1,2 lần."),
            _option("prosody", "speed_very_fast", "Rất nhanh", "Tốc độ khoảng 1,4 lần."),
            _option("prosody", "pitch_low", "Giọng thấp", "Hạ cao độ khoảng 3 bán âm."),
            _option("prosody", "pitch_high", "Giọng cao", "Tăng cao độ khoảng 2,5 bán âm."),
            _option(
                "prosody",
                "expressive_high",
                "Biểu cảm cao",
                "Tăng độ biến hóa và nhấn nhá.",
            ),
            _option(
                "prosody",
                "expressive_low",
                "Biểu cảm thấp",
                "Giữ cách đọc phẳng và trung tính hơn.",
            ),
            _option(
                "prosody",
                "pause",
                "Nghỉ ngắn",
                "Tạo khoảng nghỉ khoảng 0,4–0,7 giây.",
                usage="chèn đúng tại vị trí cần ngắt câu.",
                featured=True,
            ),
            _option(
                "prosody",
                "long_pause",
                "Nghỉ dài",
                "Tạo khoảng nghỉ khoảng 0,7–1,5 giây.",
                usage="chèn đúng tại vị trí cần ngắt ý dài.",
                featured=True,
            ),
        ),
    ),
    HiggsTagGroup(
        key="sfx",
        label="SFX giọng nói",
        description="Tạo hiệu ứng bằng chính giọng đọc, không phải âm thanh trộn ngoài.",
        options=(
            _option("sfx", "cough", "Ho", "Tạo tiếng ho hoặc hắng giọng.", usage=_SFX_USAGE),
            _option("sfx", "laughter", "Cười", "Tạo tiếng cười.", usage=_SFX_USAGE),
            _option("sfx", "crying", "Khóc", "Tạo tiếng khóc, nghẹn.", usage=_SFX_USAGE),
            _option("sfx", "screaming", "La hét", "Tạo tiếng hét.", usage=_SFX_USAGE),
            _option("sfx", "burping", "Ợ", "Tạo tiếng ợ.", usage=_SFX_USAGE),
            _option("sfx", "humming", "Ngân nga", "Tạo tiếng ngân hoặc ậm ừ.", usage=_SFX_USAGE),
            _option("sfx", "sigh", "Thở dài", "Tạo tiếng thở dài.", usage=_SFX_USAGE),
            _option("sfx", "sniff", "Sụt sịt", "Tạo tiếng hít mũi.", usage=_SFX_USAGE),
            _option("sfx", "sneeze", "Hắt hơi", "Tạo tiếng hắt hơi.", usage=_SFX_USAGE),
        ),
    ),
)


def higgs_tag_groups() -> tuple[HiggsTagGroup, ...]:
    return HIGGS_TAG_GROUPS


def featured_higgs_tags() -> tuple[HiggsTagOption, ...]:
    return tuple(
        option
        for group in HIGGS_TAG_GROUPS
        for option in group.options
        if option.featured
    )


def higgs_tag_values(category: str) -> tuple[str, ...]:
    return tuple(
        option.value
        for group in HIGGS_TAG_GROUPS
        for option in group.options
        if option.category == category
    )


EMOTIONS = higgs_tag_values("emotion")
STYLES = higgs_tag_values("style")
SOUND_EFFECTS = higgs_tag_values("sfx")
PROSODY = higgs_tag_values("prosody")
