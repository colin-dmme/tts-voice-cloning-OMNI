"""Provider-independent text boundaries used by punctuation-aware engines.

The GUI only edits millisecond values.  This module owns the punctuation
classification so Core chunk joins and the Piper worker agree on exactly which
pause applies.  A provider must explicitly advertise support before these
values are used.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PunctuationPauseConfig:
    sentence_ms: int = 320
    comma_ms: int = 90
    clause_ms: int = 180
    ellipsis_ms: int = 450

    def as_dict(self) -> dict[str, int]:
        return {
            "sentence_ms": max(0, int(self.sentence_ms)),
            "comma_ms": max(0, int(self.comma_ms)),
            "clause_ms": max(0, int(self.clause_ms)),
            "ellipsis_ms": max(0, int(self.ellipsis_ms)),
        }


@dataclass(frozen=True)
class PunctuationSegment:
    text: str
    pause_after_ms: int = 0


# A boundary is accepted only before whitespace/end. This avoids splitting
# decimal numbers such as 3.14 or 3,14 and most dotted abbreviations.
_BOUNDARY_PATTERN = re.compile(
    r"(?P<ellipsis>\.{3,}|…+)"
    r"|(?P<sentence>[!?。！？]+|(?<!\d)\.|\.(?!\d))"
    r"|(?P<comma>(?<!\d)[,，]|[,，](?!\d))"
    r"|(?P<clause>[;:；：])"
)
_CLOSING_MARKS = "\"'”’»)]}"


def split_with_punctuation_pauses(
    text: str,
    config: PunctuationPauseConfig,
) -> list[PunctuationSegment]:
    """Split text after supported punctuation while retaining the punctuation."""
    source = str(text or "").strip()
    if not source:
        return []

    matches = list(_effective_boundaries(source))
    if not matches:
        return [PunctuationSegment(source)]

    segments: list[PunctuationSegment] = []
    start = 0
    for match, end in matches:
        part = source[start:end].strip()
        if part:
            segments.append(
                PunctuationSegment(part, _pause_for_kind(match.lastgroup, config))
            )
        start = end
        while start < len(source) and source[start].isspace():
            start += 1

    remainder = source[start:].strip()
    if remainder:
        segments.append(PunctuationSegment(remainder))
    elif segments:
        # No silence is needed after the final spoken fragment. Paragraph/chunk
        # joining owns the pause that follows it.
        last = segments[-1]
        segments[-1] = PunctuationSegment(last.text, 0)
    return segments


def pause_after_text(text: str, config: PunctuationPauseConfig) -> int | None:
    """Return the matching pause for terminal punctuation, else ``None``."""
    source = str(text or "").rstrip()
    while source and source[-1] in _CLOSING_MARKS:
        source = source[:-1].rstrip()
    if not source:
        return None
    matches = list(_BOUNDARY_PATTERN.finditer(source))
    if not matches or matches[-1].end() != len(source):
        return None
    return _pause_for_kind(matches[-1].lastgroup, config)


def _effective_boundaries(text: str):
    for match in _BOUNDARY_PATTERN.finditer(text):
        end = match.end()
        while end < len(text) and text[end] in _CLOSING_MARKS:
            end += 1
        if end == len(text) or text[end].isspace():
            yield match, end


def _pause_for_kind(kind: str | None, config: PunctuationPauseConfig) -> int:
    if kind == "ellipsis":
        return max(0, int(config.ellipsis_ms))
    if kind == "comma":
        return max(0, int(config.comma_ms))
    if kind == "clause":
        return max(0, int(config.clause_ms))
    return max(0, int(config.sentence_ms))
