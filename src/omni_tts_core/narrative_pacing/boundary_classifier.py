"""Classify paragraph boundaries from the text on either side.

Discourse markers drive the tiers, one marker set per language (Vietnamese,
English). Other languages fall back to question/length rules only. "auto" is
resolved from the text itself (see resolve_language).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from omni_tts_shared.narrative_pacing import NarrativePacingOptions

# Next paragraph opens a new sub-topic or an enumerated point.
_SUBTOPIC_VI = re.compile(
    r"^(Trước hết|Từ đó|Từ đây|Đến đây|Tiếp theo|Sang đoạn|Câu hỏi thứ|Đến câu hỏi|"
    r"Điểm thứ|Ưu điểm|Điều thứ|Ngoài ra|Rồi đến|Thế còn|Còn về|Bây giờ|Trở lại|"
    r"Sau cùng|Sau đó|Một hướng|Một chủ đề|Nhìn chung|Như vậy, qua|Trước khi|"
    r"Vậy nếu|Vậy rốt cuộc|Bên cạnh|Thứ nhất|Thứ hai|Thứ ba|Cuối cùng|Phần|Chương)",
    re.IGNORECASE,
)
# Markers that usually begin a larger movement: good places for music.
_STRONG_VI = re.compile(
    r"^(Bây giờ|Trở lại|Từ đây|Từ đó, chúng ta|Đến đây|Trước khi|Vậy nếu|"
    r"Chúng ta hãy|Trước hết, chúng ta hãy|Còn về|Phần|Chương|Sau cùng)",
    re.IGNORECASE,
)
# Next paragraph continues the same thought.
_CONNECTOR_VI = re.compile(
    r"^(Bởi |Vì thế|Vì vậy|Cho nên|Nói cách khác|Nghĩa là|Thế nhưng|Nhưng|Và |"
    r"Huống chi|Quả vậy|Thực ra|Thật ra|Đó là|Đó cũng|Điều ấy|Điều này|Chính vì|"
    r"Cũng |Dẫu vậy|Tuy nhiên|Như vậy|Do đó)",
    re.IGNORECASE,
)
# Series/channel introduction right after the hook.
_INTRO_VI = re.compile(
    r"^(Đây là|Chào mừng|Xin chào|Bạn đang nghe|Các bạn đang nghe|Quý vị đang nghe|"
    r"Mình là|Tôi là)|\b(series|podcast|kênh|chương trình|tập này)\b",
    re.IGNORECASE,
)
_CLOSING_VI = re.compile(
    r"(tạm khép lại|khép lại|lời cuối|hẹn gặp lại|cảm ơn .{0,40}(lắng nghe|theo dõi))",
    re.IGNORECASE,
)
# English equivalents. Word boundaries keep "Now" from matching "Nowhere".
_SUBTOPIC_EN = re.compile(
    r"^(First(ly)?|Second(ly)?|Third(ly)?|Next|Then|Now|Finally|Lastly|In addition|"
    r"Additionally|Moreover|Furthermore|Another|Let's (turn|move|look|talk|go)|Turning to|"
    r"Moving on|Back to|Coming back|Before we|So what|What about|As for|"
    r"On the other hand|Part|Chapter|Step \d|The (first|second|third|next|last|final))\b",
    re.IGNORECASE,
)
_STRONG_EN = re.compile(
    r"^(Now|So now|Let's (turn|move|start|begin|talk about)|Turning to|Moving on|Back to|"
    r"Coming back|Before we|What about|As for|Part|Chapter|Finally)\b",
    re.IGNORECASE,
)
_CONNECTOR_EN = re.compile(
    r"^(So,|So |But |And |Because\b|That's why|That is why|This is why|In other words|"
    r"Which means|This means|Therefore|Thus|Hence|However|Yet |Still,|Even so|Indeed|"
    r"In fact|Actually|That said|Of course|After all)",
    re.IGNORECASE,
)
_INTRO_EN = re.compile(
    r"^(Welcome|Hello and welcome|Hi,? (everyone|and welcome)|This is|You're listening|"
    r"You are listening|I'm your host|My name is)|\b(podcast|episode|channel|series|show)\b",
    re.IGNORECASE,
)
_CLOSING_EN = re.compile(
    r"(thanks? (you )?for (listening|watching|joining)|see you next|until next time|"
    r"that's (all|it) for (today|this episode|now)|to wrap (this )?up|that wraps up|"
    r"signing off|take care,? and)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Markers:
    subtopic: re.Pattern | None
    strong: re.Pattern | None
    connector: re.Pattern | None
    intro: re.Pattern
    closing: re.Pattern


_MARKERS = {
    "vi": Markers(_SUBTOPIC_VI, _STRONG_VI, _CONNECTOR_VI, _INTRO_VI, _CLOSING_VI),
    "en": Markers(_SUBTOPIC_EN, _STRONG_EN, _CONNECTOR_EN, _INTRO_EN, _CLOSING_EN),
}
# Languages without a marker set keep question/length tiers; English intro and
# closing phrases are the usual ones in mixed podcasts.
_FALLBACK = Markers(None, None, None, _INTRO_EN, _CLOSING_EN)
# Letters only Vietnamese uses among Latin scripts.
_VI_LETTERS = re.compile(r"[đăâêôơưĐĂÂÊÔƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]")

SHORT_LINE_CHARS = 90


def resolve_language(language: str, text: str = "") -> str:
    """Normalise a language code; "auto" (or empty) is guessed from the text."""
    code = (language or "auto").lower().split("-")[0]
    if code != "auto":
        return code
    sample = text[:4000]
    if not sample.strip() or _VI_LETTERS.search(sample):
        return "vi"
    return "en" if re.search(r"[A-Za-z]", sample) else "other"


def markers_for(language: str) -> Markers:
    code = (language or "auto").lower().split("-")[0]
    # Entry points resolve "auto" from the text first; a bare "auto" keeps the
    # original Vietnamese behaviour.
    return _MARKERS.get("vi" if code == "auto" else code, _FALLBACK)


def boundary_kind(prev_text: str, next_text: str, language: str) -> str:
    prev_text, next_text = prev_text.strip(), next_text.strip()
    markers = markers_for(language)
    if markers.subtopic and markers.subtopic.match(next_text):
        return "subtopic"
    if len(prev_text) < SHORT_LINE_CHARS or len(next_text) < SHORT_LINE_CHARS:
        return "emphasis"
    if prev_text.endswith(("?", "？")):
        return "question"
    if markers.connector and markers.connector.match(next_text):
        return "connector"
    return "paragraph"


def starts_with_connector(text: str, language: str = "vi") -> bool:
    connector = markers_for(language).connector
    return bool(connector and connector.match(text.strip()))


def target_pause_ms(kind: str, options: NarrativePacingOptions) -> int:
    return {
        "section": options.section_pause_ms,
        "subtopic": options.subtopic_pause_ms,
        "emphasis": options.emphasis_pause_ms,
        "question": options.question_pause_ms,
        "connector": options.connector_pause_ms,
    }.get(kind, options.paragraph_pause_ms)


def bridge_strength(prev_text: str, next_text: str, language: str) -> int:
    """0 = weak spot for music, 3 = clear change of movement."""
    next_text = next_text.strip()
    markers = markers_for(language)
    if markers.strong and markers.strong.match(next_text):
        return 3
    if markers.subtopic and markers.subtopic.match(next_text):
        return 2
    return 1 if prev_text.strip().endswith(("?", "？")) else 0


def looks_like_intro(text: str, language: str) -> bool:
    head = text.strip()[:120]
    return bool(markers_for(language).intro.search(head))


def looks_like_closing(text: str, language: str) -> bool:
    head = text.strip()[:160]
    return bool(markers_for(language).closing.search(head))
