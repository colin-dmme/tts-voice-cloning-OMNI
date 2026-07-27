from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

from omni_tts_shared.errors import ConfigError


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".srt"}
_HIGGS_TOKEN_PATTERN = re.compile(r"<\|[a-z][a-z0-9_]*:[a-z][a-z0-9_]*\|>", re.IGNORECASE)


@dataclass(frozen=True)
class SourceUnit:
    index: int
    text: str


def read_source_text(path: Path, *, preserve_higgs_tags: bool = False) -> str:
    if not path.exists():
        raise ConfigError(f"Không tìm thấy file nguồn: {path}")
    if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_TEXT_EXTENSIONS))
        raise ConfigError(f"File nguồn chưa được hỗ trợ. Định dạng hiện có: {allowed}")
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".srt":
        return strip_srt_markup(content, preserve_higgs_tags=preserve_higgs_tags)
    return content.strip()


def count_source_text_chars(path: Path) -> int:
    return len(read_source_text(path))


def read_source_units(path: Path, *, preserve_higgs_tags: bool = False) -> list[SourceUnit]:
    if not path.exists():
        raise ConfigError(f"Không tìm thấy file nguồn: {path}")
    if path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_TEXT_EXTENSIONS))
        raise ConfigError(f"File nguồn chưa được hỗ trợ. Định dạng hiện có: {allowed}")
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".srt":
        return parse_srt_units(content, preserve_higgs_tags=preserve_higgs_tags)
    return paragraph_units(content)


def strip_srt_markup(content: str, *, preserve_higgs_tags: bool = False) -> str:
    lines = []
    for block in _srt_blocks(content):
        lines.extend(
            _srt_text_lines(block, preserve_higgs_tags=preserve_higgs_tags)
        )
    return "\n".join(lines)


def parse_srt_units(
    content: str, *, preserve_higgs_tags: bool = False
) -> list[SourceUnit]:
    units = []
    for block in _srt_blocks(content):
        lines = _srt_text_lines(block, preserve_higgs_tags=preserve_higgs_tags)
        text = " ".join(lines).strip()
        if text:
            units.append(SourceUnit(index=len(units) + 1, text=text))
    return units


def _srt_blocks(content: str) -> list[str]:
    normalized = content.replace("\r", "\n").strip()
    if not normalized:
        return []
    return re.split(r"\n\s*\n", normalized)


def _srt_text_lines(
    block: str, *, preserve_higgs_tags: bool = False
) -> list[str]:
    raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(raw_lines) >= 2 and raw_lines[0].isdigit() and "-->" in raw_lines[1]:
        raw_lines = raw_lines[1:]

    lines = []
    for line in raw_lines:
        if "-->" in line:
            continue
        protected: dict[str, str] = {}
        if preserve_higgs_tags:
            def protect(match: re.Match) -> str:
                key = f"___HIGGS_TOKEN_{len(protected):04d}___"
                protected[key] = match.group(0)
                return key

            line = _HIGGS_TOKEN_PATTERN.sub(protect, line)
        line = re.sub(r"<[^>]+>", "", line)
        for key, token in protected.items():
            line = line.replace(key, token)
        line = line.strip()
        if line:
            lines.append(line)
    return lines


def paragraph_units(content: str) -> list[SourceUnit]:
    normalized = content.replace("\r", "\n").strip()
    parts = re.split(r"\n\s*\n+", normalized)
    units = []
    for part in parts:
        text = " ".join(part.split()).strip()
        if text:
            units.append(SourceUnit(index=len(units) + 1, text=text))
    return units


def text_units_from_blank_lines(content: str) -> list[SourceUnit]:
    return paragraph_units(content)
