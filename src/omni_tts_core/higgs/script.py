from __future__ import annotations

import re
from dataclasses import dataclass

from omni_tts_core.text.splitter import split_text
from omni_tts_core.text.vi_normalizer import normalize_vietnamese_text
from omni_tts_shared.schemas import HiggsTtsOptions


EMOTIONS = (
    "elation",
    "amusement",
    "enthusiasm",
    "determination",
    "pride",
    "contentment",
    "affection",
    "relief",
    "contemplation",
    "confusion",
    "surprise",
    "awe",
    "longing",
    "arousal",
    "anger",
    "fear",
    "disgust",
    "bitterness",
    "sadness",
    "shame",
    "helplessness",
)
STYLES = ("singing", "shouting", "whispering")
SOUND_EFFECTS = (
    "cough",
    "laughter",
    "crying",
    "screaming",
    "burping",
    "humming",
    "sigh",
    "sniff",
    "sneeze",
)
PROSODY = (
    "speed_very_slow",
    "speed_slow",
    "speed_fast",
    "speed_very_fast",
    "pause",
    "long_pause",
    "pitch_low",
    "pitch_high",
    "expressive_high",
    "expressive_low",
)

TAG_PATTERN = re.compile(
    r"<\|(?P<category>[a-z][a-z0-9_]*):(?P<value>[a-z][a-z0-9_]*)\|>",
    re.IGNORECASE,
)
CONTROL_TOKEN_PATTERN = re.compile(r"<\|[^<>]*?\|>")
_VALID_VALUES = {
    "emotion": frozenset(EMOTIONS),
    "style": frozenset(STYLES),
    "sfx": frozenset(SOUND_EFFECTS),
    "prosody": frozenset(PROSODY),
}
_DELIVERY_ORDER = ("emotion", "style", "speed", "pitch", "expressiveness")


@dataclass(frozen=True)
class HiggsScriptIssue:
    offset: int
    token: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class HiggsScriptAnalysis:
    tag_count: int
    issues: tuple[HiggsScriptIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def summary(self) -> str:
        if not self.issues:
            return f"Higgs script hợp lệ · {self.tag_count} tag."
        errors = sum(issue.severity == "error" for issue in self.issues)
        warnings = len(self.issues) - errors
        return (
            f"Đã đọc {self.tag_count} tag · {errors} lỗi · {warnings} cảnh báo."
        )


def validate_higgs_script(text: str) -> HiggsScriptAnalysis:
    issues: list[HiggsScriptIssue] = []
    valid_spans: set[tuple[int, int]] = set()
    tag_count = 0
    for match in TAG_PATTERN.finditer(text):
        tag_count += 1
        valid_spans.add(match.span())
        category = match.group("category").lower()
        value = match.group("value").lower()
        if value not in _VALID_VALUES.get(category, frozenset()):
            issues.append(
                HiggsScriptIssue(
                    match.start(),
                    match.group(0),
                    f"Tag Higgs không được hỗ trợ: {category}:{value}.",
                )
            )
            continue
        if category == "sfx":
            following = text[match.end() : match.end() + 24]
            if not following or following[0].isspace():
                issues.append(
                    HiggsScriptIssue(
                        match.start(),
                        match.group(0),
                        "SFX nên đặt sát ngay trước từ tượng thanh, ví dụ "
                        "<|sfx:laughter|>Haha.",
                        "warning",
                    )
                )
    for match in CONTROL_TOKEN_PATTERN.finditer(text):
        if match.span() not in valid_spans:
            issues.append(
                HiggsScriptIssue(
                    match.start(),
                    match.group(0),
                    "Token có cú pháp không hợp lệ; cần dạng <|category:value|>.",
                )
            )
    return HiggsScriptAnalysis(tag_count, tuple(issues))


def normalize_higgs_text(text: str, language: str) -> str:
    """Normalize spoken fragments while keeping Higgs control tokens byte-exact."""
    if language != "vi":
        return text.strip()
    output: list[str] = []
    cursor = 0
    for match in TAG_PATTERN.finditer(text):
        output.append(_normalize_fragment(text[cursor : match.start()]))
        output.append(match.group(0))
        cursor = match.end()
    output.append(_normalize_fragment(text[cursor:]))
    return "".join(output).strip()


def compile_higgs_chunks(
    text: str,
    language: str,
    max_chars: int,
    options: HiggsTtsOptions | None = None,
) -> list[str]:
    """Compile one source unit into independent, state-complete Higgs turns."""
    normalized = normalize_higgs_text(text, language)
    if not normalized:
        return []
    raw_chunks = split_text(normalized, max_chars)
    if not raw_chunks:
        return []

    state = delivery_defaults(options)
    compiled: list[str] = []
    for raw in raw_chunks:
        leading = _leading_delivery_categories(raw)
        prefix = "".join(
            state[category]
            for category in _DELIVERY_ORDER
            if category in state and category not in leading
        )
        turn = f"{prefix}{raw.strip()}"
        compiled.append(turn)
        for match in TAG_PATTERN.finditer(raw):
            category = delivery_category(match.group("category"), match.group("value"))
            if category:
                state[category] = match.group(0)
    return compiled


def apply_delivery_defaults(text: str, options: HiggsTtsOptions | None) -> str:
    """Apply missing legacy baseline controls without overriding authored tags."""
    clean = text.strip()
    defaults = delivery_defaults(options)
    if not defaults:
        return clean
    leading = _leading_delivery_categories(clean)
    prefix = "".join(
        defaults[category]
        for category in _DELIVERY_ORDER
        if category in defaults and category not in leading
    )
    return f"{prefix}{clean}"


def delivery_defaults(options: HiggsTtsOptions | None) -> dict[str, str]:
    if options is None:
        return {}
    result: dict[str, str] = {}
    structured = (
        ("emotion", options.emotion, "emotion"),
        ("style", options.style, "style"),
        ("speed", options.speed, "prosody"),
        ("pitch", options.pitch, "prosody"),
        ("expressiveness", options.expressiveness, "prosody"),
    )
    for state_category, value, token_category in structured:
        if value:
            result[state_category] = f"<|{token_category}:{value}|>"
    # Older preferences exposed one raw prefix field. Preserve only delivery
    # controls here; positional pause/SFX must remain authored in the script.
    for match in TAG_PATTERN.finditer(options.delivery_tags):
        category = delivery_category(match.group("category"), match.group("value"))
        if category and category not in result:
            result[category] = match.group(0)
    return result


def delivery_category(category: str, value: str) -> str | None:
    category = category.lower()
    value = value.lower()
    if category in {"emotion", "style"}:
        return category
    if category != "prosody":
        return None
    if value.startswith("speed_"):
        return "speed"
    if value.startswith("pitch_"):
        return "pitch"
    if value.startswith("expressive_"):
        return "expressiveness"
    return None


def _leading_delivery_categories(text: str) -> set[str]:
    categories: set[str] = set()
    cursor = 0
    for match in TAG_PATTERN.finditer(text):
        if text[cursor : match.start()].strip():
            break
        category = delivery_category(match.group("category"), match.group("value"))
        if category:
            categories.add(category)
        cursor = match.end()
    return categories


def _normalize_fragment(fragment: str) -> str:
    if not fragment:
        return ""
    leading = " " if fragment[:1].isspace() else ""
    trailing = " " if fragment[-1:].isspace() else ""
    core = normalize_vietnamese_text(fragment)
    if not core:
        return leading if leading and trailing else ""
    return f"{leading}{core}{trailing}"
