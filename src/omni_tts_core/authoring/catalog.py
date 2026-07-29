from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoringChoice:
    value: str
    label: str
    tooltip: str


CONTENT_TYPES = (
    AuthoringChoice(
        "science_explainer",
        "Khoa học / giải thích",
        "Giải thích chính xác, thông minh; biểu cảm có tiết chế.",
    ),
    AuthoringChoice(
        "documentary",
        "Tài liệu",
        "Thuyết minh có chiều sâu, nhịp rõ và đáng tin cậy.",
    ),
    AuthoringChoice(
        "storytelling",
        "Kể chuyện",
        "Ưu tiên nhịp kể, chuyển cảm xúc và không khí.",
    ),
    AuthoringChoice(
        "advertising",
        "Quảng cáo",
        "Tập trung lợi ích, nhấn điểm nhớ và lời kêu gọi hành động.",
    ),
    AuthoringChoice(
        "conversation",
        "Hội thoại",
        "Tự nhiên, gần gũi và phản ứng đúng ngữ cảnh.",
    ),
    AuthoringChoice("custom", "Tùy chỉnh", "Dùng chỉ dẫn riêng của người dùng."),
)

PLATFORMS = (
    AuthoringChoice("youtube", "YouTube dài", "Nhịp đủ rõ cho video nội dung dài."),
    AuthoringChoice(
        "short_video",
        "YouTube Shorts / TikTok",
        "Nhanh vào trọng tâm nhưng không cường điệu mọi câu.",
    ),
    AuthoringChoice(
        "podcast",
        "Podcast / audiobook",
        "Ưu tiên nghe lâu không mệt và chuyển ý mượt.",
    ),
)

SEGMENT_ROLES = (
    AuthoringChoice("hook", "Mở đầu / hook", "Gây tò mò và đặt vấn đề, chưa diễn như cao trào."),
    AuthoringChoice("explanation", "Giải thích", "Rõ ràng, logic và ưu tiên khả năng hiểu."),
    AuthoringChoice("reveal", "Tiết lộ / đính chính", "Nhấn đúng điểm đảo nhận thức hoặc sự thật chính."),
    AuthoringChoice("transition", "Chuyển ý", "Giúp người nghe nhận ra chủ đề đang đổi."),
    AuthoringChoice("climax", "Cao trào", "Cho phép cường độ cao hơn nhưng vẫn có kiểm soát."),
    AuthoringChoice("conclusion", "Kết luận / CTA", "Chốt thông điệp hoặc dẫn sang hành động tiếp theo."),
)

NARRATOR_STYLES = (
    AuthoringChoice("neutral", "Trung tính", "Ít tag, rõ và không phô diễn."),
    AuthoringChoice("engaging", "Cuốn hút", "Có nhấn điểm quan trọng nhưng không quá kịch."),
    AuthoringChoice("calm", "Bình tĩnh", "Nhịp vững, mềm và dễ nghe lâu."),
    AuthoringChoice("energetic", "Năng lượng", "Nhanh, sáng và chủ động hơn."),
    AuthoringChoice("dramatic", "Kịch tính", "Tương phản và khoảng nghỉ mạnh hơn."),
)

TAG_DENSITIES = (
    AuthoringChoice("very_light", "Rất nhẹ", "Chỉ điều khiển ở các điểm tu từ quan trọng nhất."),
    AuthoringChoice("light", "Nhẹ · khuyên dùng", "Đủ hướng diễn nhưng vẫn tự nhiên."),
    AuthoringChoice("medium", "Vừa", "Nhiều chỉ dẫn hơn để thử nghiệm cách thể hiện."),
)

VOICE_PRESENTATIONS = (
    AuthoringChoice("auto", "Đọc từ profile", "Dùng metadata và mô tả đã lưu của giọng."),
    AuthoringChoice("female", "Giọng nữ", "Định hướng cách thể hiện phù hợp với giọng nữ."),
    AuthoringChoice("male", "Giọng nam", "Định hướng cách thể hiện phù hợp với giọng nam."),
    AuthoringChoice("neutral", "Trung tính", "Không đặt giả định nam hoặc nữ."),
)


def brief_choices() -> dict[str, tuple[AuthoringChoice, ...]]:
    return {
        "content_type": CONTENT_TYPES,
        "platform": PLATFORMS,
        "segment_role": SEGMENT_ROLES,
        "narrator_style": NARRATOR_STYLES,
        "tag_density": TAG_DENSITIES,
        "voice_presentation": VOICE_PRESENTATIONS,
    }
